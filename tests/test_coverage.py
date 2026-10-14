"""Published catalog invariants; no network, no dependence on exact moving prices."""

from pathlib import Path

from plates.models import Catalog, Snapshot

ROOT = Path(__file__).resolve().parents[1]


def test_published_scale_and_market_separation():
    data = Snapshot.model_validate_json((ROOT / "data/latest.json").read_text())
    offers = [o for s in data.sources for o in s.offers]
    known = [o for o in offers if o.sale_unit != "unknown"]
    assert len(known) >= 250
    assert len({o.source_id for o in known}) >= 10
    assert all(o.pack_evidence for o in known)
    assert all(o.currency == ("USD" if o.market == "US" else "EUR") for o in offers)


def test_reviewed_and_automated_sources_never_overlap():
    catalog = Catalog.model_validate_json((ROOT / "catalog.json").read_text())
    reviewed = Snapshot.model_validate_json((ROOT / "reviewed/latest.json").read_text())
    assert not {s.id for s in catalog.sources} & {s.id for s in reviewed.sources}
    assert len([s for s in catalog.sources if s.feeds]) >= 5
    assert next(s for s in catalog.sources if s.id == "singularwod-es").paused
    assert next(s for s in reviewed.sources if s.id == "hampton-us").status == "failed"


def test_reviewed_decimal_labels_and_pack_total_regressions():
    snapshot = Snapshot.model_validate_json((ROOT / "reviewed/latest.json").read_text())
    offers = {o.id: o for s in snapshot.sources for o in s.offers}
    assert str(offers["ruster-es:31563"].total_weight_kg) in ("0.25", "0.250")
    assert offers["sveltus-eu:2123:0"].total_weight_kg == 60
    assert all(o.currency != "GBP" for o in offers.values())
