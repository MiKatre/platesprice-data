"""Synthetic whole-catalog cases. No requests, reviewed IDs, or shipping weights."""

from decimal import Decimal

import pytest

from plates.models import LB_KG, Offer
from plates.normalize import normalize_product
from tests.conftest import AT


def product(title="Olympic Weight Plates", variant="20 kg", body="", **extra):
    return {
        "title": title,
        "handle": "olympic-weight-plates",
        "body_html": body,
        "variants": [{"id": 987, "title": variant, "price": "100.00", "available": True}],
        **extra,
    }


def normalized(source, data, **kwargs):
    offers, issues = normalize_product(source, data, AT, **kwargs)
    assert not issues
    assert len(offers) == 1
    Offer.model_validate_json(offers[0].model_dump_json())
    return offers[0]


def unknown(source, data):
    offer = normalized(source, data)
    assert offer.sale_unit == "unknown"
    assert offer.components == []
    assert offer.total_weight_kg is None
    assert offer.price_per_kg is None
    assert offer.price_per_lb is None
    assert offer.pack_evidence is None
    return offer


@pytest.mark.parametrize(
    "variant,title,body,count,weight,unit",
    [
        ("20kg (Pair)", "Olympic Plates", "", 2, "20", "kg"),
        ("45 LB single", "Iron Plates", "", 1, "45", "lb"),
        ("20 kg (piece)", "Weight Plates", "", 1, "20", "kg"),
        ("20kg", "Olympic Plates (Pair)", "", 2, "20", "kg"),
        ("20kg", "Olympic Plates", "<p>Sold in pairs.</p>", 2, "20", "kg"),
        ("20kg", "Olympic Plates", "Sold individually.", 1, "20", "kg"),
        ("Default Title", "20 kg Iron Plate (single)", "", 1, "20", "kg"),
        ("2,5 kg", "Discos olímpicos", "Precio por unidad.", 1, "2.5", "kg"),
        ("10 kg", "Disco de hierro", "Se venden por unidad.", 1, "10", "kg"),
        ("10 kg", "Discos olímpicos", "Se venden por parejas.", 2, "10", "kg"),
        ("20kg", "Hantelscheiben", "Verkauf paarweise.", 2, "20", "kg"),
        ("20 kg", "Hantelscheibe", "Preis pro Stück.", 1, "20", "kg"),
        ("10 kg", "Gewichtsscheiben", "Einzeln verkauft.", 1, "10", "kg"),
        ("2 x 20kg", "Olympic Plates", "", 2, "20", "kg"),
        ("2×20 kg", "Olympic Plates", "", 2, "20", "kg"),
        ("20kg x 2", "Olympic Plates", "", 2, "20", "kg"),
        ("2 plates of 20 kg", "Olympic Plates", "", 2, "20", "kg"),
        ("2 discos de 20 kg", "Discos olímpicos", "", 2, "20", "kg"),
        ("20 kg pair", "Plates", "Sold individually or in sets.", 2, "20", "kg"),
        ("20 kg single", "Plates (single or set)", "", 1, "20", "kg"),
    ],
)
def test_explicit_multilingual_packs(source, variant, title, body, count, weight, unit):
    offer = normalized(source, product(title, variant, body))
    assert offer.sale_unit == ("single" if count == 1 else "pair")
    assert [(c.weight, c.unit, c.count) for c in offer.components] == [
        (Decimal(weight), unit, count)
    ]
    assert offer.total_weight_kg == Decimal(weight) * count * (LB_KG if unit == "lb" else 1)
    assert offer.price_per_kg == (offer.price / offer.total_weight_kg).quantize(Decimal("0.000001"))
    assert offer.price_per_lb == (offer.price / offer.total_weight_kg * LB_KG).quantize(
        Decimal("0.000001")
    )
    assert 0 < len(offer.pack_evidence) <= 90
    assert offer.pack_evidence in " ".join((variant, title, body))


@pytest.mark.parametrize(
    "variant,title,body,total,counts",
    [
        ("2 x 20kg + 2 x 10kg", "Plates", "", "60", [2, 2]),
        ("4 x 5 lb", "Iron Plates", "", "9.07184740", [4]),
        ("Set", "Plates", "Includes 2 x 20kg and 2 x 10kg.", "60", [2, 2]),
        ("60 kg set", "Plates", "Includes 2 x 20kg + 2 x 10kg.", "60", [2, 2]),
        ("Set", "Plates 2 x 20kg + 2 x 10kg", "", "60", [2, 2]),
        ("Set", "Plates", "2 plates of 20 kg + 2 plates of 10 kg", "60", [2, 2]),
        ("Set", "Plates", "Total 60kg: 2 x 20kg + 2 x 10kg", "60", [2, 2]),
    ],
)
def test_exact_sets(source, variant, title, body, total, counts):
    offer = normalized(source, product(title, variant, body))
    assert offer.sale_unit == "set"
    assert offer.total_weight_kg == Decimal(total)
    assert [c.count for c in offer.components] == counts


@pytest.mark.parametrize(
    "variant,title,body",
    [
        ("20kg", "Weight Plates", ""),
        ("Default Title", "20kg Weight Plates", ""),
        ("100kg set", "Weight Plates", ""),
        ("20kg", "Weight Plates", "Sold individually or in pairs."),
        ("20kg", "Weight Plates", "Single or set available."),
        ("20kg single or pair", "Weight Plates", "Sold individually."),
        ("20kg", "Weight Plates", "Sold not in pairs."),
        ("20kg", "Weight Plates", "Not sold in pairs."),
        ("20kg", "Discos", "No se venden por parejas."),
        ("20kg", "Hantelscheiben", "Nicht paarweise verkauft."),
        ("40kg pair total", "Weight Plates", ""),
        ("20kg", "Weight Plates", "Pair weight: 40kg."),
        ("Pair", "Weight Plates", "20kg pair total weight."),
        ("20kg / 10kg Pair", "Weight Plates", ""),
        ("20kg (44lb) Pair", "Weight Plates", ""),
        ("45lb (20.4kg) single", "Weight Plates", ""),
        ("20kg", "Weight Plates (44lb) Pair", ""),
        ("2x20kg + 10kg", "Weight Plates", ""),
        ("2x20kg + 2x10lb", "Weight Plates", ""),
        ("Pair", "Weight Plates", "Weights: 5kg, 10kg, 20kg. Sold in pairs."),
        ("Set", "Weight Plates", "20kg, 10kg, 5kg plates."),
        ("60kg set", "Weight Plates", "Set A: 2x20kg. Set B: 2x10kg."),
        ("Set", "Weight Plates", "<table><tr><td>2x20kg</td><td>2x10kg</td></tr></table>"),
        ("20kg single", "Weight Plates Pair", ""),
        ("20kg pair", "Weight Plates", "Sold individually."),
        ("2x20kg single", "Weight Plates", ""),
        ("20kg set", "Weight Plates", "Sold individually."),
        ("100kg set", "Weight Plates", "2x20kg + 2x10kg"),
        ("0kg pair", "Weight Plates", ""),
        ("501kg single", "Weight Plates", ""),
        ("101x1kg", "Weight Plates", ""),
        ("0x20kg", "Weight Plates", ""),
        ("20kg", "Weight Plates 10kg Pair", ""),
        ("20kg pair", "Weight Plates", "10kg plates sold in pairs."),
        ("2x20kg", "Weight Plates", "2x10kg"),
        ("2x20kg", "Weight Plates (single)", ""),
        ("20kg pair", "Weight Plates", "Not sold in pairs."),
        ("20kg pair", "Weight Plates", "40kg total per pair."),
        ("20kg pair", "Weight Plates (44lb / 20kg)", ""),
        ("2x20kg or 2x10kg", "Weight Plates", ""),
        ("2x20kg / 2x10kg", "Weight Plates", ""),
        ("Set", "Weight Plates", "Includes 1x20kg"),
        ("20kg", "Weight Plates", "5kg pair, 10kg pair, 20kg pair."),
        ("40kg", "Weight Plates", "Sold in pairs. Total weight: 40kg."),
        ("40kg pair", "Weight Plates", "Sold in pairs. Total weight: 40kg."),
        ("2 pairs of 20kg", "Weight Plates", ""),
        ("2 x pair 20kg", "Weight Plates", ""),
        ("Default Title", "Weight Plates", "Shipping weight: 20kg. Sold individually."),
        ("Default Title", "Weight Plates", "Capacity 200kg. Sold individually."),
        ("1,000kg single", "Weight Plates", ""),
        ("Single-sided 20kg", "Weight Plates", ""),
    ],
)
def test_ambiguous_packs_are_retained_without_math(source, variant, title, body):
    unknown(source, product(title, variant, body))


def test_shipping_weights_and_sibling_variants_are_never_evidence(source):
    data = product(body="Our plates are great.")
    data["weight"] = 20000
    data["variants"][0].update(grams=20000, weight=20, weight_unit="kg")
    unknown(source, data)
    data["variants"].append({"id": 988, "title": "20kg Pair", "price": "200"})
    offers, issues = normalize_product(source, data, AT)
    assert not issues
    assert [o.sale_unit for o in offers] == ["unknown", "pair"]


@pytest.mark.parametrize(
    "title,product_type,body",
    [
        ("T shirt", "Clothing", "Great for lifting plates"),
        ("Plate Storage Rack", "", ""),
        ("Weight Plate Tree", "", ""),
        ("Plate Holder", "", ""),
        ("Plate Adapter", "", ""),
        ("Plate loaded machine", "", ""),
        ("Weight Plates and Barbell", "", ""),
        ("Barbell & Weight Plates Set", "", ""),
        ("Olympic bar and plates", "", ""),
        ("Discos + barra", "", ""),
        ("Weight Plate Set with 20kg Olympic Bar", "", ""),
        ("Hantelscheiben mit Langhantel", "", ""),
        ("Weight Plates", "Dumbbells", ""),
        ("Vibration Plate", "", ""),
        ("Dinner Plates", "", ""),
        ("Weight Plate Set", "", "Includes 2x20kg plates and an Olympic bar."),
        ("Weight Plate Set", "", "Contains 2x20kg plates with a rack."),
        ("Weight Plate Set", "", "Includes 2x2.5kg plates and an Olympic bar."),
        ("Weight Plate Set", "", "<ul><li>2x20kg plates</li><li>1x20kg barbell</li></ul>"),
        ("Discos", "", "Incluye 2x20kg y barra."),
    ],
)
def test_non_plate_products_and_equipment_bundles_are_excluded(source, title, product_type, body):
    assert normalize_product(
        source, product(title, "2x20kg", body, product_type=product_type), AT
    ) == ([], [])


def test_product_type_qualification_and_bar_compatibility(source):
    offer = normalized(
        source,
        product("Competition Series", "20kg Pair", "Fits Olympic bars.", product_type="Plates"),
    )
    assert offer.plate_type == "unknown"
    normalized(source, product("Olympic Barbell Plates", "20kg Pair"))


@pytest.mark.parametrize(
    "title,kind",
    [
        ("Iron Plates", "iron"),
        ("Discos de hierro", "iron"),
        ("Bumper Plates", "bumper"),
        ("Rubber Coated Plates", "rubber_coated"),
        ("Gummierte Hantelscheiben", "rubber_coated"),
        ("Urethane Plates", "urethane"),
        ("Fractional Change Plates", "change"),
        ("Olympic Plates", "unknown"),
        ("Rubber Plates", "unknown"),
    ],
)
def test_plate_material_is_not_invented(source, title, kind):
    assert normalized(source, product(title, "20kg single")).plate_type == kind


@pytest.mark.parametrize(
    "bad_price", [None, True, False, "", "bad", "NaN", "Infinity", 0, -1, "0.00", "1000001", {}, []]
)
def test_bad_price_isolated_per_variant(source, bad_price):
    data = product(variant="20kg pair")
    data["variants"] += [
        {"id": 988, "title": "10kg single", "price": bad_price},
        {"id": 989, "title": "5kg single", "price": "10.99"},
    ]
    offers, issues = normalize_product(source, data, AT)
    assert [o.id for o in offers] == ["test:987", "test:989"]
    assert len(issues) == 1 and "test:988" in issues[0]
    assert offers[1].price == Decimal("10.99")


@pytest.mark.parametrize(
    "bad",
    [
        None,
        [],
        "variant",
        {},
        {"id": True},
        {"id": "//evil"},
        {"id": 998, "title": None, "price": "10"},
    ],
)
def test_malformed_variant_isolated(source, bad):
    data = product(variant="20kg pair")
    data["variants"].insert(0, bad)
    offers, issues = normalize_product(source, data, AT)
    assert len(offers) == len(issues) == 1
    assert offers[0].id == "test:987"


def test_duplicate_ids_quarantined_but_all_other_variants_normalized(source):
    data = product(variant="20kg pair")
    data["variants"] += [dict(data["variants"][0])] + [
        {"id": i, "title": f"{i - 999}kg single", "price": "10"} for i in range(1000, 1030)
    ]
    offers, issues = normalize_product(source, data, AT)
    assert len(offers) == 30 and len(issues) == 2
    assert all(o.variant_id != "987" for o in offers)
    assert {o.variant_id for o in offers}.isdisjoint(v.id for v in source.products[0].variants)


@pytest.mark.parametrize("available", [True, False, None, "false", "true", 0, 1, [], {}])
def test_availability_requires_actual_bool(source, available):
    data = product(variant="20kg pair")
    data["variants"][0]["available"] = available
    offer = normalized(source, data)
    assert offer.available is (available if type(available) is bool else None)
    assert offer.stock_status == "unknown"


def test_source_metadata_price_timestamp_and_url_preserved(source):
    data = product(variant="45lb Pair", url="https://evil.test/elsewhere")
    source.tax_basis = "included"
    offer = normalized(source, data)
    assert offer.observed_at == AT
    assert offer.source_id == source.id and offer.currency == source.currency
    assert offer.tax_basis == "included"
    assert offer.source_url == "https://plates.test/products/olympic-weight-plates?variant=987"
    assert offer.price == Decimal("100.00")
    assert offer.shipping_price is None and offer.delivered_price is None
    assert offer.price_per_lb == Decimal("1.111111")


@pytest.mark.parametrize(
    "handle",
    [
        None,
        "",
        "https://evil.test/x",
        "//evil.test",
        "../x",
        "x/../y",
        "x?variant=1",
        "x#y",
        "x%2fy",
        "x\\y",
        "x y",
    ],
)
def test_handles_cannot_escape_origin_or_product_path(source, handle):
    offers, issues = normalize_product(source, product(handle=handle), AT)
    assert not offers and len(issues) == 1


@pytest.mark.parametrize("key", ["currency", "price_currency", "priceCurrency"])
def test_product_currency_mismatch_rejected_and_variant_mismatch_isolated(source, key):
    data = product(**{key: "EUR"})
    offers, issues = normalize_product(source, data, AT)
    assert not offers and len(issues) == 1
    data.pop(key)
    data["variants"].append({"id": 988, "title": "10kg single", "price": "20", key: "CAD"})
    offers, issues = normalize_product(source, data, AT)
    assert len(offers) == len(issues) == 1
    assert offers[0].variant_id == "987"


def test_eur_source_and_explicit_matching_currency(source):
    source.market, source.currency = "ES", "EUR"
    offer = normalized(source, product("Discos", "20kg", "Precio por unidad", currency="EUR"))
    assert offer.currency == "EUR" and offer.market == "ES"


def test_js_minor_units_and_major_unit_json(source):
    data = product(variant="20kg single")
    data["variants"][0]["price"] = 12345
    assert normalized(source, data, adapter="shopify_js").price == Decimal("123.45")
    data["variants"][0]["price"] = "123.45"
    assert normalized(source, data).price == Decimal("123.45")


@pytest.mark.parametrize("price", ["12345", 123.45, True, 0, -1, "NaN"])
def test_js_rejects_non_integer_or_nonpositive_prices(source, price):
    data = product()
    data["variants"][0]["price"] = price
    offers, issues = normalize_product(source, data, AT, adapter="shopify_js")
    assert not offers and len(issues) == 1


@pytest.mark.parametrize(
    "sku,expected",
    [("  PLATE-20  ", "PLATE-20"), ("", None), ("  ", None), (123, None), (None, None)],
)
def test_sku_trimmed_without_deduplication(source, sku, expected):
    data = product()
    data["variants"][0]["sku"] = sku
    data["variants"].append({**data["variants"][0], "id": 988})
    offers, issues = normalize_product(source, data, AT)
    assert not issues and len(offers) == 2
    assert all(o.sku == expected for o in offers)


@pytest.mark.parametrize(
    "body,count",
    [
        ("Plates are sold individually, not in pairs.", 1),
        ("Not sold individually; sold in pairs.", 2),
        ("Not in pairs. Each plate is sold individually.", 1),
        ("Weights: 5kg, 10kg, 20kg. All plates are sold in pairs.", 2),
        ("Available in 5kg, 10kg, 20kg. Plates are sold individually.", 1),
        ("<p>Sold individually.</p><table><tr><td>5kg</td><td>20kg</td></tr></table>", 1),
        ("<table><tr><td>5kg</td><td>20kg</td></tr></table><p>Sold in pairs.</p>", 2),
        ("Precio por unidad. Pesos disponibles: 5kg, 10kg, 20kg.", 1),
        ("Se venden por unidad, no por parejas.", 1),
        ("Paarweise verkauft, nicht einzeln.", 2),
    ],
)
def test_global_body_sale_quantity_is_independent_of_weight_lists(source, body, count):
    offer = normalized(source, product(variant="20kg", body=body))
    assert offer.components[0].count == count
    assert offer.total_weight_kg == 20 * count
    assert offer.pack_evidence in body


@pytest.mark.parametrize(
    "body",
    [
        "Some plates are sold individually, others sold in pairs.",
        "Some plates are sold individually.",
        "Plates may be sold individually.",
        "Plates are sold individually or in sets.",
        "Sold individually. Also available as pairs.",
        "Sold individually. Sold in pairs.",
        "Price per plate. Sold in pairs.",
        "Depending on the option, sold in pairs.",
        "Sold individually except for the larger plates.",
        "5kg plates are sold individually. 20kg plates come in a set.",
    ],
)
def test_qualified_or_conflicting_body_sale_quantities_stay_unknown(source, body):
    unknown(source, product(variant="20kg", body=body))


@pytest.mark.parametrize("variant", ["20kg pair", "2x20kg"])
def test_explicit_selection_cannot_override_conflicting_global_policy_in_table_body(
    source, variant
):
    unknown(
        source,
        product(
            variant=variant,
            body=("Sold individually.<table><tr><td>5kg</td><td>20kg</td></tr></table>"),
        ),
    )


def test_global_body_quantity_cannot_supply_mass_from_weight_list(source):
    unknown(source, product(variant="Default Title", body="5kg, 10kg. Sold individually."))


def test_resolved_single_option_can_use_one_title_mass(source):
    offer = normalized(source, product("20kg Plates single or set", "Single"))
    assert offer.total_weight_kg == 20 and offer.sale_unit == "single"


def test_body_tables_do_not_override_explicit_selected_variant(source):
    data = product(variant="2x20kg", body="<table><tr><td>4x10kg</td></tr></table>")
    assert normalized(source, data).total_weight_kg == 40


@pytest.mark.parametrize("variants", [None, {}, "bad"])
def test_malformed_product_variant_container(source, variants):
    offers, issues = normalize_product(source, product(variants=variants), AT)
    assert not offers and len(issues) == 1


def test_unsupported_adapter_is_reported(source):
    offers, issues = normalize_product(source, product(), AT, adapter="unknown")
    assert not offers and len(issues) == 1
