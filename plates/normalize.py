"""Conservative, offline Shopify catalog normalization (no reviewed-ID allowlist).

Only explicit sale quantities authorize unit-price arithmetic. Shipping weights,
other variants, and body tables never supply a selected variant's composition.
"""

import html
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit

from .models import LB_KG, Component, Offer, Source

_NUMBER = r"\d+(?:[.,]\d+)?"
_UNIT = r"(?:kgs?|kilograms?|kilogramos?|lbs?|pounds?|libras?)"
_MASS = re.compile(rf"(?<![\w.,])({_NUMBER})\s*({_UNIT})\b", re.I)
_COMPOSITION = re.compile(
    rf"(?<![\w.,])(?:(\d+)\s*(?:[x×*]|(?:plates?|discos?|scheiben)\s*(?:of|de|à|a|zu))"
    rf"\s*({_NUMBER})\s*({_UNIT})\b|"
    rf"({_NUMBER})\s*({_UNIT})\s*[x×*]\s*(\d+)\b)",
    re.I,
)
_PLATE = re.compile(r"\b(?:plates?|discos?|hantelscheiben?|gewichtsscheiben?)\b", re.I)
_ACCESSORY = re.compile(
    r"\b(?:racks?|storage|trees?|holders?|hangers?|stands?|organizers?|adapters?|"
    r"collars?|clamps?|dumbbells?|kettlebells?|machines?|trolleys?|carts?|pins?|"
    r"vests?|vibration|dinner|license|bags?|shel(?:f|ves)|stackers?|keychains?|coasters?|"
    r"attachments?|sleeves?|handlebars?|cables?|towers?|dividers?|pivot|foot|skid|press|"
    r"soportes?|almacenamiento|mancuernas?|"
    r"máquinas?|cierres?|hantelständer|ablage|kurzhanteln?|ständer)\b",
    re.I,
)
_BAR = r"(?:bars?|barbells?|barras?|langhanteln?|hantelstangen?)"
_BAR_BUNDLE = re.compile(
    rf"\b{_BAR}\b\s*(?:and|with|&|\+|y|con|und|mit)\b|"
    rf"(?:\b(?:and|with|y|con|und|mit)\b|[+&])\s*(?:an?\s+|olympic\s+)?{_BAR}\b|"
    rf"\b{_BAR}\b.*\b(?:bundle|package|set|kit)\b",
    re.I,
)
_INCLUDED_EQUIPMENT = re.compile(
    rf"\b(?:includes?|contains?|comes? with|incluye|incluyen|contiene|enthält|inklusive)\b"
    rf"(?:[^.;\n]|\.(?=\d)){{0,300}}\b(?:{_BAR}|racks?|stands?|soportes?|dumbbells?)\b|"
    rf"\b\d+\s*[x×]\s*(?:{_NUMBER}\s*{_UNIT}\s*)?"
    rf"(?:olympic\s+)?(?:{_BAR}|racks?|stands?|soportes?|dumbbells?)\b",
    re.I,
)
_PAIR = re.compile(r"\b(?:pairs?|paar(?:e|weise)?|pareja(?:s)?)\b", re.I)
_SINGLE = re.compile(
    r"\b(?:singles?|individually|individually sold|per (?:plate|piece|unit)|"
    r"sold (?:as |by )?(?:a |one |the )?(?:piece|unit)|piece|pc|"
    r"price is for one plate|por (?:unidad|disco)|individual(?:mente)?|pro stück|einzeln)\b",
    re.I,
)
_SET = re.compile(r"\b(?:sets?|bundles?|packs?|juegos?|conjuntos?|kits?)\b", re.I)
_NEGATION = re.compile(
    r"\b(?:not|never|no|nicht|kein\w*)\b.{0,35}\b"
    r"(?:pairs?|singles?|sets?|individually|paar\w*|parejas?|unidad|einzeln)\b",
    re.I,
)
_TOTAL = re.compile(
    r"\b(?:total|combined|gesamt\w*|pair weight|weight (?:of|per) (?:the )?pair|"
    r"peso (?:del? )?(?:par|pareja))\b",
    re.I,
)
_GENERIC = re.compile(
    r"\b(?:or|oder|o)\b|\b(?:options?|choose|available in|available as|"
    r"opciones|wahlweise|erhältlich|sizes)\b",
    re.I,
)
_QUANTITY = re.compile(r"\b(\d+)\s*(?:plates?|pieces?|discos?|scheiben|stück)\b", re.I)
_NON_PLATE_MASS = re.compile(
    r"\b(?:shipping|packaged|gross|package|versandgewicht|bruttogewicht|"
    r"peso (?:de envío|del paquete|bruto)|capacity|capacidad)\b",
    re.I,
)
_MULTIPLE_PAIRS = re.compile(r"\b(?:\d+\s*(?:[x×]\s*)?|multiple\s+)pairs?\b", re.I)
_DESIGN_SINGLE = re.compile(r"\b(?:single[ -](?:sided|grip|hole)|one-piece)\b", re.I)
_NEGATED_SALE = re.compile(
    r"\b(?:not|never|no|nicht|kein\w*)\s+"
    r"(?:(?:sold|se venden|in|as|a|por|en|werden|verkauft)\s+){0,4}"
    r"(?:pairs?|singles?|individually|sets?|paar\w*|parejas?|unidad|einzeln)\b",
    re.I,
)
_SALE = re.compile(
    r"\b(?:sold\s+(?:individually|singly|in pairs|as (?:a )?pairs?)|"
    r"(?:price|priced|prices?)\s+per (?:plate|piece|unit)|"
    r"price is for one plate|available as (?:pairs?|singles?|sets?)|"
    r"precio por unidad|se venden por (?:unidad|parejas?)|"
    r"pro stück|pro paar|paarweise|einzeln)\b",
    re.I,
)
_QUALIFIER = re.compile(
    r"\b(?:some|others?|certain|selected|depending|may|can be|except|unless|"
    r"algunos|otros|según|manche|je nach)\b",
    re.I,
)


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def _mass(number: str, unit: str) -> tuple[Decimal, str]:
    return Decimal(number.replace(",", ".")), "kg" if unit.lower().startswith("k") else "lb"


@dataclass
class _Facts:
    text: str
    masses: list[tuple[Decimal, str]] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    count: int | None = None
    set_like: bool = False
    ambiguous: bool = False
    evidence: str | None = None
    table: bool = False
    conflicting: bool = False


def _facts(text: str, *, table: bool = False) -> _Facts:
    facts = _Facts(text, table=table)
    facts.masses = [_mass(*m.groups()) for m in _MASS.finditer(text)]
    facts.set_like = bool(_SET.search(text))
    pairs, singles = list(_PAIR.finditer(text)), list(_SINGLE.finditer(text))
    compositions = list(_COMPOSITION.finditer(text))
    quantities = [
        m
        for m in _QUANTITY.finditer(text)
        if not any(c.start() <= m.start() < c.end() for c in compositions)
    ]
    counts = {2 for _ in pairs} | {1 for _ in singles}
    counts.update(int(m[1]) for m in quantities)
    facts.ambiguous = bool(
        table
        or _NEGATION.search(text)
        or _MULTIPLE_PAIRS.search(text)
        or _DESIGN_SINGLE.search(text)
        or (_NON_PLATE_MASS.search(text) and facts.masses)
        or re.search(r"\d,\d{3}\s*" + _UNIT + r"\b", text, re.I)
        or len({unit for _, unit in facts.masses}) > 1
        or len(counts) > 1
        or (singles and facts.set_like)
        or (_GENERIC.search(text) and (facts.set_like or pairs or singles or compositions))
        or (not compositions and len(set(facts.masses)) > 1)
        or (compositions and "/" in text)
    )
    if compositions:
        remainder = _COMPOSITION.sub(" ", text)
        # Uncounted masses cannot be silently dropped from a component list.
        leftovers = [_mass(*m.groups()) for m in _MASS.finditer(remainder)]
        try:
            for match in compositions:
                count, number, unit = match.group(1, 2, 3)
                if count is None:
                    number, unit, count = match.group(4, 5, 6)
                weight, unit = _mass(number, unit)
                facts.components.append(Component(weight=weight, unit=unit, count=int(count)))
        except (ValueError, ArithmeticError):
            facts.ambiguous = True
            facts.components = []
        if len({c.unit for c in facts.components}) > 1:
            facts.ambiguous = True
        total = sum(c.kg for c in facts.components)
        # Permit an explicitly labelled total alongside the full composition.
        if leftovers and not (
            len(leftovers) == 1
            and _TOTAL.search(remainder)
            and leftovers[0][0] * (LB_KG if leftovers[0][1] == "lb" else 1) == total
        ):
            facts.ambiguous = True
        component_count = sum(c.count for c in facts.components)
        if counts and counts != {component_count}:
            facts.ambiguous = True
        # A body containing several different set recipes is not one big set.
        if len(re.findall(r"\b(?:set|bundle|juego|conjunto)\b", text, re.I)) > 1:
            facts.ambiguous = True
        start, end = compositions[0].start(), compositions[-1].end()
        facts.evidence = text[start:end] if end - start <= 90 else None
        if facts.evidence is None:
            facts.ambiguous = True
    elif len(counts) == 1:
        facts.count = counts.pop()
        cue = (pairs or singles or quantities)[0]
        facts.evidence = cue.group(0)
        if facts.count != 1 and _TOTAL.search(text):
            facts.ambiguous = True
    return facts


def _body_facts(raw: str, *, selected_mass: bool, family_options: bool = False) -> _Facts:
    """Separate global sale policy from catalog weight lists and set tables.

    A short unqualified affirmative sentence can supply quantity, never mass.
    Remove negated sale clauses, not all text following a word like "not".
    """
    text = _text(raw)
    base = _facts(text, table=bool(re.search(r"<table\b", raw, re.I)))
    prose = re.sub(r"<table\b[^>]*>.*?</table>", " ", raw, flags=re.I | re.S)
    prose = re.sub(r"</(?:p|div|li|h[1-6])>|<br\s*/?>", ". ", prose, flags=re.I)
    prose = _text(prose)
    affirmative = _NEGATED_SALE.sub(lambda m: " " * len(m[0]), prose)
    sales = list(_SALE.finditer(affirmative))
    if not sales:
        return base
    sentences = re.split(r"(?<=[.!?;])\s+", affirmative)
    sale_sentences = [s for s in sentences if _SALE.search(s)]
    qualified = any(_QUALIFIER.search(s) or _GENERIC.search(s) for s in sale_sentences)
    policy = " ".join(sale_sentences)
    counts = {1 for _ in _SINGLE.finditer(policy)} | {2 for _ in _PAIR.finditer(policy)}
    mixed = len(counts) != 1 or bool(_SET.search(policy))
    if qualified or mixed:
        base.ambiguous = True
        # Explicit disagreement is different from a selectable single-or-set menu.
        base.conflicting = len(counts) > 1 and not (
            _GENERIC.search(affirmative) or _QUALIFIER.search(affirmative)
        )
        return base
    if (
        selected_mass
        and not any(_MASS.search(s) or _TOTAL.search(s) for s in sale_sentences)
        and (family_options or not _COMPOSITION.search(prose))
    ):
        return _Facts(
            affirmative,
            count=counts.pop(),
            evidence=sales[0][0],
        )
    # Without an independently selected mass, body lists/tables remain unusable.
    # Still permit a clear affirmative policy after a negated alternative.
    if not base.table:
        return _facts(affirmative)
    return base


def _sale_unit(components: list[Component]) -> str:
    count = sum(c.count for c in components)
    if count == 1:
        return "single"
    if count == 2 and len(components) == 1:
        return "pair"
    return "set"


def _pack(
    variant: str,
    title: str,
    body: str,
    *,
    family_options: bool = False,
) -> tuple[list[Component], str | None]:
    # Family ranges are not the selected plate's mass (5–25kg != a 25kg plate).
    title_facts = re.sub(
        rf"{_NUMBER}\s*(?:{_UNIT})?\s*[-–]\s*{_NUMBER}\s*{_UNIT}\b",
        "",
        title,
        flags=re.I,
    )
    if family_options and not _SET.search(variant):
        title_facts = re.sub(
            rf"(?:&|\bor\b)\s*(?:{_NUMBER}\s*{_UNIT}\s*)?sets?\b",
            "",
            title_facts,
            flags=re.I,
        )
    levels = [_facts(variant), _facts(title_facts)]
    mass_facts = next((f for f in levels if f.masses), None)
    levels.append(
        _body_facts(
            body,
            selected_mass=bool(
                (mass_facts and not mass_facts.ambiguous and len(set(mass_facts.masses)) == 1)
                or any(f.components and not f.ambiguous for f in levels)
            ),
            family_options=family_options and not levels[0].set_like,
        )
    )
    # Selection-local ambiguity must never be repaired with generic product prose.
    if levels[0].ambiguous:
        return [], None
    selected = levels[0]
    # Product titles describe this item, not a family of unrelated table rows.
    # Conflicting title/selection masses (including lb/kg parentheticals) are not
    # conversions. A named set total is checked against its exact recipe below.
    if (
        selected.masses
        and levels[1].masses
        and not selected.set_like
        and not levels[1].set_like
        and set(selected.masses) != set(levels[1].masses)
    ):
        return [], None
    for index, facts in enumerate(levels):
        if facts.ambiguous:
            # A resolved variant can override a generic single-or-set description.
            # Otherwise ambiguity at a more specific level blocks fallback.
            return [], None
        if facts.components:
            components = facts.components
            if index and selected.masses:
                expected = {(c.weight, c.unit) for c in components}
                total_kg = sum(c.kg for c in components)
                selected_total = (
                    len(selected.masses) == 1
                    and (selected.set_like or _TOTAL.search(selected.text))
                    and selected.masses[0][0] * (LB_KG if selected.masses[0][1] == "lb" else 1)
                    == total_kg
                )
                if set(selected.masses) != expected and not selected_total:
                    return [], None
            if (
                any(f.set_like for f in levels[: index + 1])
                and sum(c.count for c in components) < 2
            ):
                return [], None
            if selected.count and selected.count != sum(c.count for c in components):
                return [], None
            if _conflicts(components, levels[index + 1 :]):
                return [], None
            return components, facts.evidence
        if facts.count is not None:
            # A bare "set" selection cannot inherit the single/pair buying option.
            if any(f.set_like for f in levels[:index]) or facts.set_like:
                return [], None
            masses = next((f.masses for f in levels[: index + 1] if f.masses), [])
            if not masses:
                # Title/body may supply one mass, but never a multi-option table.
                mass_facts = next((f for f in levels[index + 1 :] if f.masses), None)
                if mass_facts and (
                    not mass_facts.ambiguous
                    or (
                        _GENERIC.search(mass_facts.text)
                        and not mass_facts.table
                        and len(set(mass_facts.masses)) == 1
                        and not _NON_PLATE_MASS.search(mass_facts.text)
                        and not _NEGATION.search(mass_facts.text)
                    )
                ):
                    masses = mass_facts.masses
            if len(set(masses)) != 1:
                return [], None
            if any(_TOTAL.search(f.text) for f in levels[: index + 1]):
                return [], None
            try:
                weight, unit = masses[0]
                components = [Component(weight=weight, unit=unit, count=facts.count)]
                if _conflicts(components, levels[index + 1 :]):
                    return [], None
                return components, facts.evidence
            except ValueError:
                return [], None
    return [], None


def _conflicts(components: list[Component], lower_levels: list[_Facts]) -> bool:
    """Never let precedence erase an explicit contradictory pack statement."""
    count = sum(c.count for c in components)
    signature = Counter((c.weight, c.unit, c.count) for c in components)
    for lower in lower_levels:
        if lower.conflicting:
            return True
        if _NEGATION.search(lower.text):
            return True
        if lower.table:
            continue
        if lower.ambiguous:
            if _GENERIC.search(lower.text):
                continue  # Generic options are not the selected variant.
            if lower.count or lower.components or len({u for _, u in lower.masses}) > 1:
                return True
            continue
        if lower.count is not None and (
            (lower.count > 1 and _TOTAL.search(lower.text) and _MASS.search(lower.text))
            or lower.count != count
            or (lower.masses and set(lower.masses) != {(c.weight, c.unit) for c in components})
        ):
            return True
        if (
            lower.components
            and Counter((c.weight, c.unit, c.count) for c in lower.components) != signature
        ):
            return True
    return False


def _plate_type(title: str, product_type: str, variant: str) -> str:
    text = f"{title} {product_type} {variant}".casefold()
    for kind, pattern in (
        ("change", r"\b(?:change|fractional|micro|fraccionales)\b"),
        ("urethane", r"\b(?:urethane|polyurethane|uretano|poliuretano)\b"),
        ("bumper", r"\bbumpers?\b"),
        (
            "rubber_coated",
            r"\b(?:rubber[ -](?:coated|encased)|gummiert\w*|"
            r"recubiertos? de (?:goma|caucho))\b",
        ),
        ("iron", r"\b(?:iron|cast[ -]iron|hierro|gusseisen)\b"),
    ):
        if re.search(pattern, text):
            return kind
    return "unknown"


def _equipment(text: str) -> bool:
    # "Barbell plates" and compatibility language do not include a bar. Other
    # bar mentions in a product/variant name are too risky for plate-only math.
    without_compatibility = re.sub(
        rf"\b(?:for|fits?|compatible with|para|für)\s+(?:olympic\s+|olímpicas?\s+)?{_BAR}\b",
        "",
        text,
        flags=re.I,
    )
    without_compatibility = re.sub(
        r"\bbarbell\s+(?:weight\s+)?plates?\b", "plates", without_compatibility, flags=re.I
    )
    return bool(
        _ACCESSORY.search(text)
        or _BAR_BUNDLE.search(text)
        or re.search(rf"\b{_BAR}\b", without_compatibility, re.I)
    )


def _currency(obj: dict, expected: str) -> None:
    for key in ("currency", "price_currency", "priceCurrency"):
        if key in obj and obj[key] != expected:
            raise ValueError("unexpected currency in product/variant")


def _price(raw: object, adapter: str) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
        raise ValueError("invalid price")
    if adapter == "shopify_js" and not isinstance(raw, int):
        raise ValueError("Shopify JS price must be integer minor units")
    price = Decimal(str(raw))
    if adapter == "shopify_js":
        price /= 100
    if not price.is_finite() or not 0 < price <= 1_000_000:
        raise ValueError("price outside supported range")
    return price


def normalize_product(
    source: Source, product: dict, at: datetime, *, adapter: str = "shopify_json"
) -> tuple[list[Offer], list[str]]:
    """Normalize every plate variant; return recoverable errors separately.

    The caller confirms the storefront currency. Explicit contradictory currency
    fields still fail closed. Unknown packs remain useful price/availability rows.
    """
    offers, issues = [], []
    try:
        if adapter not in {"shopify_json", "shopify_js"}:
            raise ValueError("unsupported Shopify adapter")
        if not isinstance(product, dict):
            raise ValueError("product must be an object")
        title = _text(product.get("title"))
        product_type = _text(product.get("product_type"))
        qualification = f"{title} {product_type}"
        if not title or not _PLATE.search(qualification):
            return [], []
        raw_body = product.get("body_html") or product.get("description") or ""
        body = _text(raw_body)
        # Merchants often use mixed departments ("Bars, Plates and Collars").
        # A retailer name containing "Barbell" is not bundled equipment either.
        unbranded = re.sub(r"^" + re.escape(source.name) + r"\s+", "", title, flags=re.I)
        if (
            _equipment(unbranded)
            or (_equipment(product_type) and not _PLATE.search(product_type))
            or _INCLUDED_EQUIPMENT.search(body)
        ):
            return [], []
        _currency(product, source.currency)
        handle = product.get("handle")
        if not isinstance(handle, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", handle):
            raise ValueError("invalid product handle")
        url = f"{source.origin.rstrip('/')}/products/{handle}"
        if urlsplit(url).netloc != urlsplit(source.origin).netloc:
            raise ValueError("product URL must share source origin")
        variants = product.get("variants")
        if not isinstance(variants, list):
            raise ValueError("variants must be a list")
    except (ValueError, TypeError, ArithmeticError) as exc:
        return [], [f"{source.id}: product: {exc}"]

    # Do not select an arbitrary price when a feed repeats a variant ID.
    ids = Counter(str(v.get("id")) for v in variants if isinstance(v, dict))
    for index, raw in enumerate(variants):
        label = f"{source.id}: variant[{index}]"
        try:
            if not isinstance(raw, dict):
                raise ValueError("variant must be an object")
            variant_id = str(raw.get("id", ""))
            if not re.fullmatch(r"[0-9]+", variant_id):
                raise ValueError("invalid variant ID")
            label = f"{source.id}:{variant_id}"
            if ids[variant_id] > 1:
                raise ValueError("duplicate variant ID")
            if not isinstance(raw.get("title"), str) or not raw["title"].strip():
                raise ValueError("invalid variant title")
            variant_title = _text(raw["title"])
            if _equipment(variant_title):
                continue
            _currency(raw, source.currency)
            price = _price(raw.get("price"), adapter)
            components, evidence = _pack(
                variant_title,
                title,
                raw_body if isinstance(raw_body, str) else "",
                family_options=any(
                    isinstance(v, dict) and _SET.search(_text(v.get("title"))) for v in variants
                )
                and any(
                    isinstance(v, dict) and not _SET.search(_text(v.get("title"))) for v in variants
                ),
            )
            total = sum(c.kg for c in components) if components else None
            offers.append(
                Offer(
                    id=f"{source.id}:{variant_id}",
                    source_id=source.id,
                    market=source.market,
                    currency=source.currency,
                    title=title,
                    variant_title=variant_title,
                    variant_id=variant_id,
                    source_url=f"{url}?variant={variant_id}",
                    plate_type=_plate_type(title, product_type, variant_title),
                    sale_unit=_sale_unit(components) if components else "unknown",
                    components=components,
                    total_weight_kg=total,
                    price=price,
                    price_per_kg=(price / total).quantize(Decimal("0.000001")) if total else None,
                    price_per_lb=(price / total * LB_KG).quantize(Decimal("0.000001"))
                    if total
                    else None,
                    available=raw.get("available") if type(raw.get("available")) is bool else None,
                    tax_basis=source.tax_basis,
                    observed_at=at,
                    pack_evidence=evidence,
                    sku=raw["sku"].strip() or None if isinstance(raw.get("sku"), str) else None,
                    condition="b_stock"
                    if re.search(r"\b(?:b-ware|b-stock)\b", title, re.I)
                    else "used"
                    if re.search(r"\b(?:used|second[ -]hand|usad[oa]s?)\b", title, re.I)
                    else "unknown",
                )
            )
        except (ValueError, TypeError, ArithmeticError) as exc:
            issues.append(f"{label}: {exc}")
    return offers, issues
