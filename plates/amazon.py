"""Amazon trial: searches and product pages read through Cloudflare Kitesurf (remote browser).

Separate from the catalog collectors and the published snapshot until access proves reliable.
One product page per browser session: Amazon pages exceed the session memory after a few.

    uv run --locked python -m plates.amazon            # both markets
    uv run --locked python -m plates.amazon --only ES
"""

import argparse
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from plates.models import LB_KG, Component, Offer, Snapshot, SourceState
from plates.normalize import (
    _MASS,
    _NUMBER,
    _PLATE,
    _UNIT,
    _equipment,
    _mass,
    _plate_type,
    _sale_unit,
)

MARKETS = {
    "ES": {
        "id": "amazon-es",
        "name": "Amazon.es",
        "origin": "https://www.amazon.es",
        "currency": "EUR",
        "language": "es_ES",
        "terms": ["discos bumper", "discos olimpicos hierro", "discos fraccionales 50mm"],
        # Outside Spain, Amazon.es removes Spanish VAT (21%): only a Spanish delivery counts.
        "deliver": r"Spain|España|\b\d{5}\b",
    },
    "US": {
        "id": "amazon-us",
        "name": "Amazon.com",
        "origin": "https://www.amazon.com",
        "currency": "USD",
        "language": "en_US",
        "terms": ["bumper plates", "cast iron olympic plates", "olympic change plates"],
        # From abroad Amazon.com names the country and converts prices; a US visitor sees
        # "Update location" or a ZIP. One page per session leaves no room to set a ZIP first.
        "deliver": r"Update location|United States|\b\d{5}\b",
    },
}
PRODUCTS_PER_MARKET = 30
PARALLEL_SESSIONS = 3
KITESURF = os.environ.get(
    "KITESURF_CLI", str(Path(__file__).resolve().parent.parent / "kitesurf/kitesurf.mjs")
)
OUT = Path(__file__).resolve().parent.parent / "amazon"

SCRIPTS = Path(__file__).resolve().parent


def script(name: str, url: str) -> str:
    return (SCRIPTS / f"amazon_{name}.js").read_text().replace("__URL__", json.dumps(url))


_COUNT = re.compile(
    r"^(?:número de productos|number of items|número de piezas)\s*:?\s*(\d+)$", re.I
)
# Explicit plate count times mass: "2 x 5kg", "2*10kg", "5KG x 2", "COMBO (2x5kg, 2x10kg)".
_TIMES = re.compile(
    rf"(?<![\d.,])(\d+)\s*[x×*]\s*({_NUMBER})\s*({_UNIT})\b|({_NUMBER})\s*({_UNIT})\s*[x×*]\s*(\d+)\b",
    re.I,
)
_WORD_PAIR = re.compile(r"\b(?:pairs?|pareja)\b", re.I)
_WORD_SINGLE = re.compile(r"\b(?:single|unidad|1 pc)\b", re.I)
_RANGE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:kgs?|lbs?)?\s*[-–/]\s*\d+(?:[.,]\d+)?\s*(?:kgs?|lbs?)\b", re.I
)


def kitesurf(source: str) -> dict:
    run = subprocess.run(
        ["node", KITESURF], input=source, capture_output=True, text=True, timeout=180, check=False
    )
    if run.returncode:
        error = run.stderr.strip().splitlines()
        raise RuntimeError(error[0] if error else "kitesurf failed")
    return json.loads(run.stdout)


def parse_price(text: str | None, currency: str) -> Decimal | None:
    if not text:
        return None
    # Amazon converts prices for the visitor's location; never record another currency.
    if re.search(r"\$|USD" if currency == "EUR" else r"€|EUR", text):
        return None
    digits = re.sub(r"[^\d.,]", "", text)
    if currency == "EUR":
        digits = digits.replace(".", "").replace(",", ".")
    else:
        digits = digits.replace(",", "")
    try:
        value = Decimal(digits)
    except InvalidOperation:
        return None
    return value if value > 0 else None


def availability(text: str | None) -> bool | None:
    if not text:
        return None
    if re.search(r"no disponible|currently unavailable|agotado|out of stock", text, re.I):
        return False
    if re.search(r"en stock|in stock|disponible|quedan|only \d+ left", text, re.I):
        return True
    return None


def _times(text: str) -> list[Component]:
    counts: dict[tuple, int] = {}
    for m in _TIMES.finditer(text):
        count, number, unit = (m[1], m[2], m[3]) if m[1] else (m[6], m[4], m[5])
        key = _mass(number, unit)
        counts[key] = counts.get(key, 0) + int(count)
    return [Component(weight=w, unit=u, count=n) for (w, u), n in counts.items()]


def pack(title: str, selected: list[str], details: list[str]) -> tuple[list[Component], str | None]:
    """Selected size before title: "N x mass", else one mass times Amazon's item count.

    Amazon's item count describes the listing, so it never overrides an explicit "2 x 5 kg".
    A size naming a mass we cannot resolve stays unknown rather than borrowing the title's.
    """
    listed = next((int(m[1]) for d in details if (m := _COUNT.match(d))), None)
    for text in (" ".join(selected), _RANGE.sub("", title)):
        text = re.sub(r"(\d)-(?=[a-z])", r"\1 ", text, flags=re.I)  # "45-Pound"
        if components := _times(text):
            return components, text.strip()[:80]
        masses = {_mass(*m.groups()) for m in _MASS.finditer(text)}
        count = 2 if _WORD_PAIR.search(text) else 1 if _WORD_SINGLE.search(text) else listed
        if len(masses) == 1 and count and count <= 10:
            weight, unit = masses.pop()
            evidence = f"{text.strip()[:80]}; {count} item(s)"
            return [Component(weight=weight, unit=unit, count=count)], evidence
        if masses:
            break
    return [], None


def offer(market: str, asin: str, page: dict, at: datetime) -> Offer | None:
    config = MARKETS[market]
    title = page.get("title") or ""
    price = parse_price(page.get("price"), config["currency"])
    if not price or not _PLATE.search(title) or _equipment(title):
        return None
    components, evidence = pack(title, page.get("selected") or [], page.get("details") or [])
    total = sum(c.kg for c in components) if components else None
    return Offer(
        id=f"{config['id']}:{asin}",
        source_id=config["id"],
        market=market,
        currency=config["currency"],
        title=title,
        variant_title=" · ".join(page.get("selected") or []) or "Default Title",
        variant_id=asin,
        source_url=f"{config['origin']}/dp/{asin}",
        plate_type=_plate_type(title, "", " ".join(page.get("selected") or [])),
        sale_unit=_sale_unit(components) if components else "unknown",
        components=components,
        total_weight_kg=total,
        price=price,
        price_per_kg=(price / total).quantize(Decimal("0.000001")) if total else None,
        price_per_lb=(price / total * LB_KG).quantize(Decimal("0.000001")) if total else None,
        available=availability(page.get("availability")),
        tax_basis="included" if market == "ES" else "excluded",
        observed_at=at,
        pack_evidence=evidence,
        price_basis=f"Amazon buy box ({page.get('seller') or 'no seller shown'}); "
        "shipping unverified.",
    )


def collect(market: str, run=kitesurf) -> tuple[SourceState, dict]:
    config, at = MARKETS[market], datetime.now(timezone.utc)
    stats = {
        "at": at.isoformat(),
        "market": market,
        "searches": 0,
        "search_ok": 0,
        "products": 0,
        "loaded": 0,
        "retried": 0,
        "captcha": 0,
        "errors": [],
        "offers": 0,
        "per_kg": 0,
    }
    asins: dict[str, str] = {}
    for term in config["terms"]:
        stats["searches"] += 1
        url = f"{config['origin']}/s?k={term.replace(' ', '+')}&language={config['language']}"
        try:
            result = run(script("search", url))
        except Exception as exc:  # noqa: BLE001 - every failure is a trial data point
            stats["errors"].append(f"search {term}: {exc}"[:200])
            continue
        stats["captcha"] += result["captcha"]
        # Amazon prices for the remote browser's location; record where it thinks we are.
        stats["deliver_to"] = result.get("deliver")
        stats["search_ok"] += not result["captcha"]
        for item in result["results"]:
            if item["asin"] and not item["sponsored"] and _PLATE.search(item["title"]):
                asins.setdefault(item["asin"], item["title"])
    # Prices depend on where Amazon thinks the remote browser is; skip pages priced elsewhere.
    located = bool(re.search(config["deliver"], stats.get("deliver_to") or ""))
    stats["wrong_location"] = stats["search_ok"] > 0 and not located
    chosen = list(asins)[:PRODUCTS_PER_MARKET] if located else []
    stats["products"] = len(chosen)

    def product(asin):
        url = f"{config['origin']}/dp/{asin}?language={config['language']}&psc=1"
        # One retry: heavy pages sometimes crash the remote page engine.
        for retry in (False, True):
            stats["retried"] += retry
            try:
                return asin, run(script("product", url)), None
            except Exception as exc:  # noqa: BLE001
                error = f"product {asin}: {exc}"[:200]
        return asin, None, error

    offers, issues = [], []
    with ThreadPoolExecutor(PARALLEL_SESSIONS) as pool:
        for asin, page, error in pool.map(product, chosen):
            if error or page is None:
                stats["errors"].append(error)
                continue
            if page["captcha"]:
                stats["captcha"] += 1
                continue
            stats["loaded"] += 1
            try:
                if item := offer(market, asin, page, at):
                    offers.append(item)
            except ValueError as exc:
                issues.append(f"{asin}: {exc}"[:200])
    stats["offers"] = len(offers)
    stats["per_kg"] = sum(o.price_per_kg is not None for o in offers)
    state = SourceState(
        id=config["id"],
        name=config["name"],
        status="ok" if offers else "failed",
        attempted_at=at,
        last_success_at=at if offers else None,
        offers=offers,
        issues=issues,
        coverage={k: stats[k] for k in ("products", "loaded", "captcha", "offers", "per_kg")},
    )
    return state, stats


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=sorted(MARKETS))
    args = parser.parse_args(argv)
    OUT.mkdir(exist_ok=True)
    previous = OUT / "latest.json"
    states = Snapshot.model_validate_json(previous.read_text()).sources if previous.exists() else []
    for market in [args.only] if args.only else MARKETS:
        state, stats = collect(market)
        # A run seen from another country says nothing about local prices: keep the saved ones.
        if not stats["wrong_location"]:
            states = [s for s in states if s.id != state.id] + [state]
        with (OUT / "trial.jsonl").open("a") as log:
            log.write(json.dumps(stats) + "\n")
        summary = {k: v for k, v in stats.items() if k != "errors"}
        print(json.dumps(summary), f"errors={len(stats['errors'])}")
    snapshot = Snapshot(generated_at=datetime.now(timezone.utc), sources=states)
    (OUT / "latest.json").write_text(snapshot.model_dump_json(indent=1) + "\n")


if __name__ == "__main__":
    main()
