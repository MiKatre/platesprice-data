import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from plates.collect import merge_reviewed
from plates.models import Snapshot

ROOT = Path(__file__).resolve().parents[1]


def reviewed():
    return Snapshot.model_validate_json((ROOT / "reviewed/latest.json").read_text())


def test_reviewed_catalog_has_exact_pack_weights_and_derived_prices():
    data = reviewed()
    assert len(data.sources) == 3
    assert sum(len(s.offers) for s in data.sources) == 12
    offers = [o for s in data.sources for o in s.offers]
    assert all(o.pack_evidence for o in offers)
    pair = next(o for o in offers if o.price == 164)
    assert pair.total_weight_kg == 40 and pair.price_per_kg == Decimal("4.100000")
    bundle = next(o for o in offers if o.sale_unit == "set")
    assert bundle.total_weight_kg == 110 and sum(c.count for c in bundle.components) == 8
    assert all(o.available is None for o in offers if o.market == "US")


def test_merge_preserves_observation_and_review_dates_without_network():
    data = reviewed()
    before = data.model_dump_json()
    empty = Snapshot(generated_at=datetime.now(timezone.utc), sources=[])
    merged = merge_reviewed(empty, data)
    assert merged.sources == data.sources
    assert data.model_dump_json() == before
    assert merge_reviewed(empty, None) == empty
    with pytest.raises(ValueError, match="overlap"):
        merge_reviewed(merged, data)


def test_reviewed_sources_require_evidence_and_review_date():
    data = json.loads((ROOT / "reviewed/latest.json").read_text())
    data["sources"][0]["offers"][0]["pack_evidence"] = None
    with pytest.raises(ValidationError, match="pack evidence"):
        Snapshot.model_validate(data)
    data = reviewed().model_dump(mode="json")
    data["sources"][0]["reviewed_at"] = None
    with pytest.raises(ValidationError, match="review date"):
        Snapshot.model_validate(data)
