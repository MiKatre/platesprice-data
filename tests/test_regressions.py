"""Safety regressions from independent review. No network requests."""

import json
from datetime import timedelta

import httpx
import pytest

from plates.adapters import check_currency, parse_product
from plates.collect import collect_source
from plates.fetch import Fetcher, FetchError
from tests.conftest import AT
from tests.test_collect import FakeFetcher


def test_normalized_url_checked_before_request():
    hits = []

    def handler(request):
        hits.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /blocked")

    f = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), "https://plates.test")
    with pytest.raises(FetchError, match="disallows"):
        f.get("https://plates.test/public/../blocked")
    assert hits == ["/robots.txt"]


@pytest.mark.parametrize("rate", ["1/30", "1/5", "5/60 0800-1200"])
def test_request_rate_fails_closed(rate):
    def handler(request):
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, text=f"User-agent: *\nRequest-rate: {rate}")

    f = Fetcher(httpx.Client(transport=httpx.MockTransport(handler)), "https://plates.test")
    with pytest.raises(FetchError, match="Request-rate"):
        f.get("https://plates.test/product")


def test_elapsed_budget_bounds_streaming():
    clock = [0]

    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"some"
            clock[0] += 100
            yield b"more"

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, stream=SlowStream())

    f = Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "https://plates.test",
        delay=0,
        clock=lambda: clock[0],
        sleep=lambda _: None,
    )
    with pytest.raises(FetchError, match="time budget"):
        f.get("https://plates.test/product")


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", None),
        ("price", "broken"),
        ("price", 10**40),
        ("price_currency", "CAD"),
        ("currency", "EUR"),
    ],
)
def test_bad_variant_isolated_and_good_data_retained(source, product_data, field, value):
    prior = collect_source(source, FakeFetcher(product_data), now=AT)
    product_data["variants"][0][field] = value
    result = collect_source(source, FakeFetcher(product_data), prior, now=AT + timedelta(hours=1))
    assert result.status == "failed"
    assert result.offers == prior.offers
    assert result.offers[0].observed_at == AT


def test_removed_offer_not_retained(source, product_data):
    variant = source.products[0].variants[0].model_copy(deep=True)
    variant.id = "456"
    source.products[0].variants.append(variant)
    product_data["variants"].append({**product_data["variants"][0], "id": 456})
    prior = collect_source(source, FakeFetcher(product_data), now=AT)
    assert len(prior.offers) == 2
    source.products[0].variants.pop()
    result = collect_source(source, FakeFetcher(error=RuntimeError("blocked")), prior, now=AT)
    assert [o.id for o in result.offers] == ["test:123"]


def test_changed_pack_not_retained_on_failure(source, product_data):
    prior = collect_source(source, FakeFetcher(product_data), now=AT)
    source.products[0].variants[0].components[0].weight = 25
    result = collect_source(source, FakeFetcher(error=RuntimeError("blocked")), prior, now=AT)
    assert not result.offers and not result.retained_previous


def test_pack_evidence_missing_fails(source, product_data):
    source.products[0].pack_evidence = "Sold in pairs"
    with pytest.raises(ValueError, match="pack-size"):
        parse_product(source, source.products[0], json.dumps(product_data), AT)


def test_storefront_currency_required():
    check_currency('Shopify.currency = {"active":"USD","rate":"1.0"};', "USD")
    for html in ['Shopify.currency = {"active":"CAD"};', "<html>Challenge</html>"]:
        with pytest.raises(ValueError, match="currency"):
            check_currency(html, "USD")
