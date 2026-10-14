"""Synthetic fixtures only; merchant descriptions/images are not redistributed."""

from datetime import datetime, timezone

import pytest

from plates.models import Catalog

AT = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


@pytest.fixture
def source():
    return Catalog.model_validate(
        {
            "sources": [
                {
                    "id": "test",
                    "name": "Test Plates",
                    "origin": "https://plates.test",
                    "market": "US",
                    "currency": "USD",
                    "tax_basis": "excluded",
                    "currency_evidence_url": "https://plates.test/",
                    "terms_url": "https://plates.test/policies/terms-of-service",
                    "products": [
                        {
                            "url": "https://plates.test/products/bumper",
                            "data_url": "https://plates.test/products/bumper.js",
                            "adapter": "shopify_js",
                            "title": "Test Bumper Plates",
                            "plate_type": "bumper",
                            "evidence": "Synthetic: sold in pairs.",
                            "pack_evidence": "Pair",
                            "reviewed_on": "2026-10-14",
                            "variants": [
                                {
                                    "id": "123",
                                    "title": "45 LB Pair",
                                    "sale_unit": "pair",
                                    "components": [{"weight": "45", "unit": "lb", "count": 2}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ).sources[0]


@pytest.fixture
def product_data():
    return {
        "title": "Test Bumper Plates",
        "variants": [{"id": 123, "title": "45 LB Pair", "price": 12000, "available": True}],
    }
