"""Bounded whole-catalog discovery. No per-variant allowlist or network shortcuts."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal

PAGE_SIZE = 250
NORMALIZER_VERSION = 2


def catalog_signature(source):
    """Invalidate retained derived values when scope/currency/parser rules change."""
    config = {
        "origin": source.origin,
        "market": source.market,
        "currency": source.currency,
        "tax_basis": source.tax_basis,
        "feeds": [f.model_dump(mode="json") for f in source.feeds],
        "normalizer_version": NORMALIZER_VERSION,
    }
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def offer_identity(offer):
    # A shared SKU is not enough: merchants reuse it across selectable colors/sizes.
    return (offer.price, offer.components, offer.sale_unit, offer.condition, offer.variant_title)


def collect_feeds(source, fetcher, at):
    from .normalize import normalize_product

    offers, issues = [], []
    seen_products = set()
    seen_variants = {}
    seen_skus = {}
    counts = {
        "catalog_products": 0,
        "plate_products": 0,
        "priced_variants": 0,
        "confirmed_packs": 0,
        "unconfirmed_packs": 0,
        "duplicate_variants": 0,
        "truncated_feeds": 0,
    }
    for feed in source.feeds:
        previous_page_ids = None
        for page in range(1, feed.max_pages + 1):
            url = f"{feed.url}?limit={PAGE_SIZE}&page={page}"
            payload = json.loads(fetcher.get(url), parse_float=Decimal)
            observed = at
            if fetcher.documents and fetcher.documents[-1].get("observed_at"):
                observed = datetime.fromisoformat(fetcher.documents[-1]["observed_at"])
            products = payload.get("products")
            if not isinstance(products, list):
                raise ValueError("catalog response requires a products list")
            page_ids = [str(p.get("id", p.get("handle"))) for p in products]
            if products and page_ids == previous_page_ids:
                raise ValueError("catalog pagination repeated a page")
            previous_page_ids = page_ids
            for product, product_id in zip(products, page_ids, strict=True):
                if product_id in seen_products:
                    continue
                seen_products.add(product_id)
                counts["catalog_products"] += 1
                normalized, errors = normalize_product(source, product, observed)
                issues.extend(errors)
                if normalized:
                    counts["plate_products"] += 1
                for offer in normalized:
                    # Shopify aliases and overlapping collections must not inflate coverage.
                    prior = seen_variants.get(offer.id)
                    values = offer_identity(offer)
                    if prior:
                        if values != offer_identity(prior):
                            raise ValueError(f"conflicting catalog variant: {offer.id}")
                        counts["duplicate_variants"] += 1
                        continue
                    seen_variants[offer.id] = offer
                    sku = offer.sku.strip().casefold() if offer.sku else None
                    prior = next(
                        (p for p in seen_skus.get(sku, []) if values == offer_identity(p)), None
                    )
                    if prior:
                        if prior.available != offer.available:
                            prior.available = None  # Conflicting alias orderability is unknown.
                        counts["duplicate_variants"] += 1
                        continue
                    if sku:
                        seen_skus.setdefault(sku, []).append(offer)
                    offers.append(offer)
            if len(products) < PAGE_SIZE:
                break
            if page == feed.max_pages:
                counts["truncated_feeds"] += 1
                issues.append(f"catalog page cap reached: {feed.url}; coverage is incomplete")
    counts["priced_variants"] = len(offers)
    counts["confirmed_packs"] = sum(o.sale_unit != "unknown" for o in offers)
    counts["unconfirmed_packs"] = len(offers) - counts["confirmed_packs"]
    counts["issues"] = len(issues)
    return offers, counts, issues[:200]
