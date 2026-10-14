import signal
import time

import httpx
import pytest

from plates.fetch import Fetcher, FetchError


def test_blocked_headers_interrupted_and_signal_restored():
    previous = signal.getsignal(signal.SIGALRM)

    def handler(request):
        time.sleep(1)
        return httpx.Response(200, text="User-agent: *\nAllow: /")

    f = Fetcher(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "https://plates.test",
        max_seconds=0.02,
    )
    started = time.monotonic()
    with pytest.raises(FetchError, match="time budget"):
        f.get("https://plates.test/a")
    assert time.monotonic() - started < 0.5
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0
