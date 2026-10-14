import httpx
import pytest

from plates.fetch import Fetcher, FetchError


def fetcher(handler, **kwargs):
    return Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "https://plates.test",
        delay=0,
        sleep=lambda _: None,
        **kwargs,
    )


def test_wildcards_longest_allow_and_query_disallow():
    hits = []

    def handler(request):
        hits.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text=(
                    "User-agent: *\nDisallow: /*?*\nDisallow: /private/*\nAllow: /private/public$\n"
                ),
            )
        return httpx.Response(200, text="ok")

    f = fetcher(handler)
    assert f.get("https://plates.test/private/public") == "ok"
    for url in ["https://plates.test/a?secret=1", "https://plates.test/private/no"]:
        with pytest.raises(FetchError, match="disallows"):
            f.get(url)
        assert url not in hits


@pytest.mark.parametrize("code", [401, 403, 429])
def test_blocks_are_never_retried(code):
    hits = []

    def handler(request):
        hits.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(code)

    f = fetcher(handler)
    with pytest.raises(FetchError, match=str(code)):
        f.get("https://plates.test/product")
    assert hits.count("/product") == 1


def test_transient_retry_is_bounded():
    hits = []

    def handler(request):
        hits.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(503)

    with pytest.raises(FetchError, match="503"):
        fetcher(handler).get("https://plates.test/product")
    assert hits.count("/product") == 2


def test_redirect_checked_before_following():
    hits = []

    def handler(request):
        hits.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /blocked")
        return httpx.Response(302, headers={"Location": "/blocked"})

    with pytest.raises(FetchError, match="disallows"):
        fetcher(handler).get("https://plates.test/a")
    assert "https://plates.test/blocked" not in hits


def test_cross_origin_redirect_never_requested():
    hits = []

    def handler(request):
        hits.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"Location": "https://other.test/product"})

    with pytest.raises(FetchError, match="origin"):
        fetcher(handler).get("https://plates.test/a")
    assert len(hits) == 2


def test_bad_robots_fails_closed():
    def handler(request):
        return httpx.Response(200, text="<html>Challenge</html>")

    with pytest.raises(FetchError, match="recognizable"):
        fetcher(handler).get("https://plates.test/a")


def test_budget_and_size_cap(monkeypatch):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="1234567890")

    with pytest.raises(FetchError, match="budget"):
        fetcher(handler, budget=1).get("https://plates.test/a")
    monkeypatch.setattr("plates.fetch.MAX_BYTES", 5)
    with pytest.raises(FetchError, match="size"):
        fetcher(handler).get("https://plates.test/a")


def test_crawl_delay_is_respected():
    waits = []

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 7")
        return httpx.Response(200, text="ok")

    f = Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "https://plates.test",
        delay=2,
        sleep=waits.append,
        clock=lambda: 0,
    )
    f.get("https://plates.test/a")
    assert waits == [7]
