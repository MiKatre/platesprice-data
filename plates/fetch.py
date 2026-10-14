"""Bounded GETs only. No proxies, cookies, browser impersonation or block bypass."""

import hashlib
import re
import signal
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from protego import Protego

AGENT = "PlatesPrice"
USER_AGENT = "PlatesPrice/0.1 (+https://github.com/MiKatre/platesprice-data)"
MAX_BYTES = 5_000_000


class FetchError(RuntimeError):
    pass


@contextmanager
def time_limit(seconds):
    """Hard wall-clock deadline for this synchronous macOS/Linux CLI, including headers."""
    if seconds <= 0:
        raise FetchError("per-source time budget exhausted")

    def expired(*_):
        raise FetchError("per-source time budget exhausted")

    previous = signal.signal(signal.SIGALRM, expired)
    prior_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *prior_timer)
        signal.signal(signal.SIGALRM, previous)


class Fetcher:
    def __init__(
        self,
        client,
        origin,
        *,
        delay=2.0,
        budget=30,
        max_seconds=90,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.client = client
        self.origin = origin.rstrip("/")
        self.delay = delay
        self.budget = budget
        self.sleep = sleep
        self.clock = clock
        self.deadline = clock() + max_seconds
        self.last_request = None
        self.rules = None
        self.documents = []

    def _check_origin(self, url):
        parts = urlsplit(url)
        if (
            parts.scheme != "https"
            or parts.netloc != urlsplit(self.origin).netloc
            or parts.username
            or parts.fragment
        ):
            raise FetchError("URL outside the approved HTTPS origin")

    def _wait(self, seconds):
        if self.clock() + seconds >= self.deadline:
            raise FetchError("per-source time budget exhausted")
        if seconds > 0:
            self.sleep(seconds)

    def _request(self, url, *, robots=False):
        for redirect in range(4):
            # HTTPX normalizes dot segments. Check the URL that will actually be sent.
            url = str(httpx.URL(url))
            self._check_origin(url)
            if not robots and not self.rules.can_fetch(url, AGENT):
                raise FetchError(f"robots.txt disallows {url}")
            for attempt in range(2):
                if self.budget <= 0:
                    raise FetchError("per-source request budget exhausted")
                self._wait(0)
                if self.last_request is not None:
                    self._wait(max(0, self.delay - (self.clock() - self.last_request)))
                self.budget -= 1
                self.last_request = self.clock()
                # Do not carry Set-Cookie between requests or negotiate another market.
                self.client.cookies.clear()
                try:
                    with self.client.stream("GET", url, follow_redirects=False) as response:
                        status = response.status_code
                        headers = response.headers
                        if status in (401, 403, 429):
                            raise FetchError(f"HTTP {status}; stop this source, no bypass")
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            self._wait(0)
                            body.extend(chunk)
                            if len(body) > MAX_BYTES:
                                raise FetchError("response exceeds size limit")
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == 0:
                        self._wait(4)
                        continue
                    raise FetchError(type(exc).__name__) from exc
                if status in (500, 502, 503, 504) and attempt == 0:
                    self._wait(4)
                    continue
                break
            self.documents.append(
                {
                    "url": url,
                    "status": status,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
            if status in (301, 302, 303, 307, 308):
                location = headers.get("location")
                if not location or redirect == 3:
                    raise FetchError("invalid or excessive redirects")
                url = str(httpx.URL(url).join(location))
                continue
            if robots and status == 404:
                return ""
            if status != 200:
                raise FetchError(f"HTTP {status}")
            return bytes(body).decode("utf-8-sig")
        raise FetchError("too many redirects")

    def get(self, url):
        with time_limit(self.deadline - self.clock()):
            result = self._get(url)
            self._wait(0)
            return result

    def _get(self, url):
        self._check_origin(url)
        if self.rules is None:
            text = self._request(self.origin + "/robots.txt", robots=True)
            if text.strip() and "user-agent:" not in text.lower():
                raise FetchError("robots.txt is not recognizable; fail closed")
            # Protego 0.5 misparses some Request-rate values (e.g. 1/30).
            # Fail closed rather than silently exceeding the site's requested rate.
            if re.search(r"(?im)^\s*request-rate\s*:", text):
                raise FetchError("Request-rate directive needs manual review")
            self.rules = Protego.parse(text)
            delay = self.rules.crawl_delay(AGENT)
            self.delay = max(self.delay, float(delay or 0))
            if self.delay > 60:
                raise FetchError("crawl delay exceeds this collector's run budget")
        return self._request(url)
