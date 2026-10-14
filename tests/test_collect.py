import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from plates import collect
from plates.models import Catalog, Snapshot
from tests.conftest import AT


class FakeFetcher:
    documents = []

    def __init__(self, data=None, error=None):
        self.data, self.error = data, error

    def get(self, url):
        if self.error:
            raise self.error
        if url == "https://plates.test/":
            return 'Shopify.currency = {"active":"USD","rate":"1.0"};'
        return json.dumps(self.data)


def test_failure_retains_original_timestamp(source, product_data):
    first = collect.collect_source(source, FakeFetcher(product_data), now=AT)
    failed = collect.collect_source(
        source, FakeFetcher(error=RuntimeError("blocked")), first, now=AT + timedelta(days=1)
    )
    assert failed.status == "failed"
    assert failed.offers == first.offers
    assert failed.last_success_at == AT
    assert failed.retained_previous
    assert failed.offers[0].observed_at == AT


def test_price_jump_quarantined(source, product_data):
    first = collect.collect_source(source, FakeFetcher(product_data), now=AT)
    product_data["variants"][0]["price"] *= 3
    result = collect.collect_source(source, FakeFetcher(product_data), first, now=AT)
    assert result.status == "quarantined"
    assert result.offers == first.offers


def test_normal_change_updates(source, product_data):
    first = collect.collect_source(source, FakeFetcher(product_data), now=AT)
    product_data["variants"][0]["price"] = 13000
    result = collect.collect_source(source, FakeFetcher(product_data), first, now=AT)
    assert result.status == "ok" and result.offers[0].price == 130
    assert not result.retained_previous


def test_first_failure_has_no_fake_prices(source):
    result = collect.collect_source(source, FakeFetcher(error=ValueError("bad")), now=AT)
    assert result.offers == [] and result.last_success_at is None


def test_atomic_write(tmp_path):
    output = tmp_path / "data/latest.json"
    collect.atomic_json(output, {"a": 1})
    collect.atomic_json(output, {"a": 2})
    assert json.loads(output.read_text()) == {"a": 2}
    assert not list(tmp_path.rglob("*.tmp"))


def test_invalid_previous_never_overwritten(tmp_path, source):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(Catalog(sources=[source]).model_dump_json())
    output = tmp_path / "latest.json"
    output.write_text('{"schema_version":99}')
    with pytest.raises(ValidationError):
        collect.main(["--catalog", str(catalog), "--output", str(output)])
    assert output.read_text() == '{"schema_version":99}'


def test_only_preserves_unselected_source(monkeypatch, source, product_data):
    second = source.model_copy(deep=True)
    second.id = "other"
    previous = Snapshot(
        generated_at=AT,
        sources=[
            collect.collect_source(second, FakeFetcher(product_data), now=AT),
        ],
    )
    monkeypatch.setattr(collect, "Fetcher", lambda *_: FakeFetcher(product_data))
    snapshot, attempted = collect.run(Catalog(sources=[source, second]), previous, None, ["test"])
    assert len(attempted) == 1
    assert snapshot.sources[1] == previous.sources[0]


def test_partial_failure_keeps_successful_source(monkeypatch, source, product_data):
    second = source.model_copy(deep=True)
    second.id = "other"
    second.origin = "https://other.test"
    second.currency_evidence_url = "https://other.test/"
    second.terms_url = "https://other.test/terms"
    second.products[0].url = "https://other.test/products/bumper"
    second.products[0].data_url = "https://other.test/products/bumper.js"
    monkeypatch.setattr(
        collect,
        "Fetcher",
        lambda _, origin: (
            FakeFetcher(product_data)
            if origin == source.origin
            else FakeFetcher(error=RuntimeError("403"))
        ),
    )
    snapshot, attempted = collect.run(Catalog(sources=[source, second]), None, None)
    assert [s.status for s in attempted] == ["ok", "failed"]
    assert len(snapshot.sources[0].offers) == 1
