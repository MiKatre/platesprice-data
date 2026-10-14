import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from plates.adapters import parse_product
from plates.models import Catalog, Offer
from tests.conftest import AT


def test_unknown_pack_has_no_unit_prices(source, product_data):
    variant = source.products[0].variants[0]
    variant.components = []
    variant.sale_unit = "unknown"
    source.products[0].pack_evidence = None
    offer = parse_product(source, source.products[0], json.dumps(product_data), AT)[0]
    assert offer.price == 120
    assert offer.total_weight_kg is None
    assert offer.price_per_kg is None and offer.price_per_lb is None
    assert offer.stock_status == "unknown"
    data = offer.model_dump()
    data["price_per_kg"] = 1
    with pytest.raises(ValidationError):
        Offer.model_validate(data)


def test_sibling_variant_cannot_supply_pack_evidence(source, product_data):
    source.products[0].variants[0].title = "45 LB"
    product_data["variants"][0]["title"] = "45 LB"
    product_data["variants"].append(
        {"id": 999, "title": "45 LB Pair", "price": 12000, "available": True}
    )
    with pytest.raises(ValueError, match="pack-size"):
        parse_product(source, source.products[0], json.dumps(product_data), AT)


def test_checked_in_catalog_valid():
    catalog = Catalog.model_validate_json(
        (Path(__file__).resolve().parents[1] / "catalog.json").read_text()
    )
    assert catalog.sources
    for source in catalog.sources:
        # A bounded pilot; larger catalogs require an explicit request-budget review.
        assert len(source.products) <= 20
        assert all(
            v.sale_unit == "unknown" or p.pack_evidence for p in source.products for v in p.variants
        )
