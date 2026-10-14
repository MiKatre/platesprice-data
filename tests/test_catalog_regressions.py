"""Catalog replay discoveries, expressed as synthetic fixtures."""

import pytest

from plates.normalize import normalize_product
from tests.conftest import AT
from tests.test_normalize import normalized, product


@pytest.mark.parametrize(
    "title",
    [
        "Ball/Plate Shelf",
        "Plate Keychain",
        "Plate Coaster Set",
        "Mobile Plate Stacker",
        "Plate Loaded Cable Tower",
        "Adjustable Foot Plate",
        "Leg Press Plate",
        "Fractional Plate Bag",
        "Plate Sleeve",
        "Tornado Pivot Arm Metal Plate",
        "Skid Plate",
    ],
)
def test_hardware_and_merchandise_are_not_weight_plate_offers(source, title):
    assert normalize_product(source, product(title), AT) == ([], [])


def test_mixed_department_and_barbell_brand_are_not_bundles(source):
    source.name = "Example Barbell"
    offer = normalized(
        source,
        product(
            "Example Barbell Iron Plates",
            "20kg Pair",
            product_type="Bars, Plates and Collars",
        ),
    )
    assert offer.total_weight_kg == 40


@pytest.mark.parametrize("label", ["5kg", "10kg", "20kg", "25kg"])
def test_family_mass_range_does_not_override_selected_weight(source, label):
    offer = normalized(source, product("Bumper Plates | Paarweise | 5-25kg", label))
    assert offer.sale_unit == "pair"
    assert offer.total_weight_kg == int(label[:-2]) * 2


def test_b_stock_is_not_silently_presented_as_new_or_definitely_used(source):
    offer = normalized(source, product("B-WARE Iron Plates", "20kg single"))
    assert offer.condition == "b_stock"


def test_pc_label_is_explicit_single_piece(source):
    offer = normalized(source, product("10 lb Cast Iron Plate [pc]", "Default Title"))
    assert offer.sale_unit == "single"


def test_global_single_policy_is_not_a_promotional_pair_of_sleeves(source):
    offer = normalized(
        source,
        product(
            "Iron Plates",
            "20kg",
            "<p>Try a pair of single ply sleeves.</p><p>Price is for one plate, not a pair.</p>"
            "<table><tr><td>5kg</td><td>20kg</td></tr></table>",
        ),
    )
    assert offer.total_weight_kg == 20


def test_mixed_family_single_selection_can_use_explicit_sale_policy(source):
    data = product(
        "Iron Plates, 5kg-20kg & Sets",
        "20kg",
        "<p>Plates are sold individually, not in pairs.</p><p>60kg Set: 2x20kg + 2x10kg.</p>",
    )
    data["variants"].append({"id": 988, "title": "60kg Set", "price": "200"})
    offers, issues = normalize_product(source, data, AT)
    assert not issues
    assert offers[0].sale_unit == "single" and offers[0].total_weight_kg == 20
    # Generic family recipes are never blindly added across selected sets.
    assert offers[1].sale_unit == "unknown"


def test_contradictory_qualified_plural_sale_statement_is_not_ignored(source):
    offer = normalized(
        source,
        product(
            "Iron Plates",
            "20kg",
            "Sold individually. Some weights are only sold as pairs.",
        ),
    )
    assert offer.sale_unit == "unknown"
