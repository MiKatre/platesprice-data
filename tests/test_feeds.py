"""Whole-catalog ingestion regressions; synthetic responses, no network."""

import copy
import json
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from plates import feeds
from plates.collect import collect_source, retained_offers
from plates.models import Source
from tests.conftest import AT


def catalog_source(source, *, pages=4):
    data = source.model_dump(mode="json")
    data["products"] = []
    data["feeds"] = [
        {"url": "https://plates.test/collections/plates/products.json", "max_pages": pages}
    ]
    return Source.model_validate(data)


def product(ident=1, price="120.00", sku=None):
    return {
        "id": ident,
        "handle": f"bumper-{ident}",
        "title": "Olympic Bumper Plates",
        "product_type": "Weight Plates",
        "body_html": "<p>Sold in pairs.</p>",
        "variants": [
            {"id": ident, "title": "45 LB", "price": price, "available": True, "sku": sku},
        ],
    }


class FeedFetcher:
    documents = []

    def __init__(self, pages, *, error=None):
        self.pages, self.error, self.hits = pages, error, []

    def get(self, url):
        self.hits.append(url)
        if self.error:
            raise RuntimeError(self.error)
        if url == "https://plates.test/":
            return 'Shopify.currency = {"active":"USD"};'
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        return json.dumps({"products": self.pages[page - 1]})


def test_feed_models_validate_scope_and_bounds(source):
    spec = catalog_source(source)
    assert not spec.products and spec.feeds
    for updates in [
        {"feeds": []},
        {"feeds": [{"url": "https://outside.test/products.json"}]},
        {"feeds": [{"url": "https://plates.test/products.json?page=2"}]},
        {"feeds": [{"url": "https://plates.test/products.json", "max_pages": 99}]},
    ]:
        with pytest.raises(ValidationError):
            Source.model_validate({**spec.model_dump(mode="json"), **updates})


def test_pages_discover_new_variants_without_manual_ids(source, monkeypatch):
    monkeypatch.setattr(feeds, "PAGE_SIZE", 2)
    fetcher = FeedFetcher([[product(1), product(2)], [product(3)]])
    state = collect_source(catalog_source(source), fetcher, now=AT)
    assert state.status == "ok", state.error
    assert len(state.offers) == 3
    assert state.coverage["confirmed_packs"] == 3
    assert state.coverage["catalog_products"] == 3
    assert state.offers[0].total_weight_kg == Decimal("40.82331330")
    assert fetcher.hits[-1].endswith("?limit=2&page=2")


def test_cap_is_visible_and_repeated_pages_fail(source, monkeypatch):
    monkeypatch.setattr(feeds, "PAGE_SIZE", 2)
    batch = [product(1), product(2)]
    offers, counts, issues = feeds.collect_feeds(
        catalog_source(source, pages=1), FeedFetcher([batch]), AT
    )
    assert len(offers) == 2 and counts["truncated_feeds"] == 1
    assert "incomplete" in issues[0]
    with pytest.raises(ValueError, match="repeated"):
        feeds.collect_feeds(catalog_source(source), FeedFetcher([batch, batch]), AT)


def test_aliases_do_not_inflate_offer_counts(source):
    first = product(1, sku="PAIR45")
    second = product(2, sku="PAIR45")
    third = product(3, sku="DIFFERENT")
    third["variants"][0]["id"] = 1
    offers, counts, _ = feeds.collect_feeds(
        catalog_source(source), FeedFetcher([[first, second, third]]), AT
    )
    assert len(offers) == 1 and counts["duplicate_variants"] == 2


def test_bad_variant_does_not_hide_other_catalog_products(source):
    fetcher = FeedFetcher([[product(1), product(2, price="bad"), product(3)]])
    state = collect_source(catalog_source(source), fetcher, now=AT)
    assert state.status == "ok" and len(state.offers) == 2
    assert state.issues


def test_catalog_failure_retains_old_dates_only_with_matching_scope(source):
    spec = catalog_source(source)
    prior = collect_source(spec, FeedFetcher([[product()]]), now=AT)
    failed = collect_source(spec, FeedFetcher([], error="403"), prior, now=AT + timedelta(days=1))
    assert failed.status == "failed" and failed.retained_previous
    assert failed.offers[0].observed_at == AT
    changed = spec.model_copy(deep=True)
    changed.feeds[0].url = "https://plates.test/collections/other/products.json"
    assert retained_offers(changed, prior) == []


def test_price_jump_quarantines_one_variant_not_the_entire_feed(source):
    spec = catalog_source(source)
    batch = [product(1), product(2)]
    prior = collect_source(spec, FeedFetcher([batch]), now=AT)
    updated = copy.deepcopy(batch)
    updated[0]["variants"][0]["price"] = "999"
    state = collect_source(spec, FeedFetcher([updated]), prior, now=AT + timedelta(hours=1))
    assert state.status == "ok" and [o.variant_id for o in state.offers] == ["2"]
    assert state.coverage["quarantined_variants"] == 1
    assert state.coverage["priced_variants"] == 1
    assert "changed" in state.issues[-1]


def test_shared_sku_does_not_merge_distinct_selected_colors(source):
    first = product(1, sku="SAME")
    second = product(2, sku="SAME")
    first["variants"][0]["title"] = "45 LB / Black"
    second["variants"][0]["title"] = "45 LB / Red"
    third = product(3, sku="SAME")
    third["variants"][0]["title"] = "45 LB / Black"
    third["variants"][0]["available"] = False
    offers, counts, _ = feeds.collect_feeds(
        catalog_source(source), FeedFetcher([[first, second, third]]), AT
    )
    assert len(offers) == 2 and counts["duplicate_variants"] == 1
    assert offers[0].available is None


def test_paused_host_is_not_requested_even_when_selected(source, monkeypatch):
    from plates import collect
    from plates.models import Catalog, Snapshot

    spec = catalog_source(source)
    prior = collect_source(spec, FeedFetcher([[product()]]), now=AT)
    spec.paused = True
    spec.pause_reason = "Previously blocked; no retries."
    monkeypatch.setattr(collect, "Fetcher", lambda *_: pytest.fail("Paused host requested"))
    snapshot, attempted = collect.run(
        Catalog(sources=[spec]), Snapshot(generated_at=AT, sources=[prior]), None, [spec.id]
    )
    assert not attempted and snapshot.sources[0].offers == prior.offers
