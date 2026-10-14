import copy
import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from plates.adapters import parse_product
from plates.models import Catalog, Component, Offer, Variant
from tests.conftest import AT


def parse(source, data):
    return parse_product(source, source.products[0], json.dumps(data), AT)[0]


def test_pair_total_and_exact_conversion(source, product_data):
    offer = parse(source, product_data)
    assert offer.price == Decimal("120")
    assert offer.total_weight_kg == Decimal("40.82331330")
    assert offer.price_per_lb == Decimal("1.333333")
    assert offer.shipping_price is None and offer.delivered_price is None
    assert offer.shipping_status == "unknown"
    Offer.model_validate_json(offer.model_dump_json())


def test_single_kg_and_set(source, product_data):
    variant = source.products[0].variants[0]
    variant.sale_unit = "single"
    variant.components = [Component(weight="20", unit="kg", count=1)]
    assert parse(source, product_data).total_weight_kg == 20
    variant.sale_unit = "set"
    variant.components = [
        Component(weight="20", unit="kg", count=2),
        Component(weight="10", unit="kg", count=2),
    ]
    assert parse(source, product_data).total_weight_kg == 60


def test_shopify_json_uses_major_units(source, product_data):
    source.products[0].adapter = "shopify_json"
    product_data["variants"][0]["price"] = "120.25"
    assert parse(source, {"product": product_data}).price == Decimal("120.25")


@pytest.mark.parametrize("price", [0, -100, "NaN", "12.50", True])
def test_invalid_minor_unit_prices_fail(source, product_data, price):
    product_data["variants"][0]["price"] = price
    with pytest.raises((ValueError, ArithmeticError)):
        parse(source, product_data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "45 LB Single"),
        ("id", 999),
        ("available", None),
    ],
)
def test_drift_needs_review(source, product_data, field, value):
    product_data["variants"][0][field] = value
    with pytest.raises(ValueError):
        parse(source, product_data)


def test_product_drift_and_currency_fail(source, product_data):
    for key, value in [("title", "Bundle with a rack"), ("currency", "CAD")]:
        data = {**product_data, key: value}
        with pytest.raises(ValueError):
            parse(source, data)


def test_out_of_stock_is_not_deleted(source, product_data):
    product_data["variants"][0]["available"] = False
    assert parse(source, product_data).available is False


def test_unreviewed_variants_ignored(source, product_data):
    product_data["variants"].append(
        {"id": 999, "title": "Mystery set", "price": 1, "available": True}
    )
    assert len(parse_product(source, source.products[0], json.dumps(product_data), AT)) == 1


def test_duplicate_variants_fail(source, product_data):
    product_data["variants"].append(copy.deepcopy(product_data["variants"][0]))
    with pytest.raises(ValueError):
        parse(source, product_data)


def test_catalog_and_pack_validation(source):
    with pytest.raises(ValidationError):
        Variant(
            id="1",
            title="x",
            sale_unit="pair",
            components=[Component(weight=20, unit="kg", count=1)],
        )
    data = {"sources": [source.model_dump(mode="json")] * 2}
    with pytest.raises(ValidationError):
        Catalog.model_validate(data)
    data["sources"] = [data["sources"][0]]
    data["sources"][0]["products"][0]["data_url"] = "https://elsewhere.test/a"
    with pytest.raises(ValidationError):
        Catalog.model_validate(data)
