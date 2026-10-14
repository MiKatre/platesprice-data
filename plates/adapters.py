"""Read only reviewed product/variant IDs; do not infer pack sizes from feed weights."""

import html
import json
import re
from datetime import datetime
from decimal import Decimal

from .models import LB_KG, Offer, Product, Source


def check_currency(text: str, expected: str):
    match = re.search(r"Shopify\.currency\s*=\s*(\{[^;\n]+\})", text)
    if not match or json.loads(match.group(1)).get("active") != expected:
        raise ValueError("storefront currency could not be confirmed")


def parse_product(source: Source, spec: Product, text: str, at: datetime) -> list[Offer]:
    data = json.loads(text, parse_float=Decimal)
    product = data["product"] if spec.adapter == "shopify_json" else data
    if product["title"].strip() != spec.title:
        raise ValueError("product title changed; review pack contents")
    # Shopify product endpoints often omit currency. The reviewed storefront
    # establishes it; if a response does provide currency, it must agree.
    if data.get("currency", source.currency) != source.currency:
        raise ValueError("unexpected storefront currency")
    raw_variants = product["variants"]
    content = " ".join(
        [
            product["title"],
            product.get("body_html") or product.get("description") or "",
        ]
    )
    content = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", content)).split()).casefold()
    by_id = {str(v["id"]): v for v in raw_variants}
    if len(by_id) != len(raw_variants):
        raise ValueError("duplicate source variant IDs")
    offers = []
    for variant in spec.variants:
        raw = by_id.get(variant.id)
        if raw is None:
            raise ValueError(f"reviewed variant disappeared: {variant.id}")
        if raw["title"].strip() != variant.title:
            raise ValueError(f"variant title changed: {variant.id}")
        if variant.sale_unit != "unknown" and (
            not spec.pack_evidence
            or spec.pack_evidence.casefold() not in content + " " + variant.title.casefold()
        ):
            raise ValueError("pack-size evidence disappeared; review required")
        if not isinstance(raw.get("available"), bool):
            raise ValueError("stock status is missing or ambiguous")
        for obj in (data, product, raw):
            for key in ("currency", "price_currency", "priceCurrency"):
                if key in obj and obj[key] != source.currency:
                    raise ValueError("unexpected currency in product/variant")
        raw_price = raw["price"]
        if isinstance(raw_price, bool):
            raise ValueError("invalid price")
        price = Decimal(str(raw_price))
        if spec.adapter == "shopify_js":
            if not isinstance(raw_price, int):
                raise ValueError("Shopify JS price must be integer minor units")
            price /= 100
        if not price.is_finite() or not 0 < price <= 1_000_000:
            raise ValueError("price outside supported range")
        total_kg = sum(c.kg for c in variant.components) if variant.components else None
        offers.append(
            Offer(
                id=f"{source.id}:{variant.id}",
                source_id=source.id,
                market=source.market,
                currency=source.currency,
                title=spec.title,
                variant_title=variant.title,
                variant_id=variant.id,
                source_url=f"{spec.url}?variant={variant.id}",
                plate_type=spec.plate_type,
                sale_unit=variant.sale_unit,
                components=[c.model_copy(deep=True) for c in variant.components],
                total_weight_kg=total_kg,
                price=price,
                price_per_kg=(price / total_kg).quantize(Decimal("0.000001")) if total_kg else None,
                price_per_lb=(price / total_kg * LB_KG).quantize(Decimal("0.000001"))
                if total_kg
                else None,
                available=raw["available"],
                tax_basis=source.tax_basis,
                observed_at=at,
            )
        )
    return offers
