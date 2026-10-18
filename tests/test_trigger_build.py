import json
import urllib.error
from pathlib import Path

import pytest

from scripts import trigger_build as module

HOOK = "https://api.netlify.com/build_hooks/" + "b" * 24
COMMIT = "a" * 40


@pytest.fixture
def publish(monkeypatch, tmp_path):
    snapshot = Path(__file__).parents[1] / "data/latest.json"
    (tmp_path / "data").mkdir()
    (tmp_path / "data/latest.json").write_bytes(snapshot.read_bytes())
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NETLIFY_BUILD_HOOK", HOOK)
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: COMMIT + "\n")


class Response:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_sends_exact_commit_without_logging_secret(publish, monkeypatch, capsys):
    requests = []

    def send(request, **kwargs):
        requests.append(request)
        assert kwargs["timeout"] == 30
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", send)
    assert module.main([]) == 0
    assert json.loads(requests[0].data) == {"plate_data_commit": COMMIT}
    assert requests[0].get_header("Content-type") == "application/json"
    captured = capsys.readouterr()
    assert COMMIT in captured.out
    assert HOOK not in captured.out + captured.err


@pytest.mark.parametrize("status", [None, 503])
def test_hook_failure_retries_and_redacts_errors(publish, monkeypatch, capsys, status):
    attempts = []

    def send(*args, **kwargs):
        attempts.append(1)
        if status is None:
            raise urllib.error.URLError(HOOK + " unreachable")
        return Response(status)

    monkeypatch.setattr(module.urllib.request, "urlopen", send)
    monkeypatch.setattr(module.time, "sleep", lambda *a: None)
    assert module.main([]) == 1
    assert len(attempts) == 3
    captured = capsys.readouterr()
    assert HOOK not in captured.out + captured.err


@pytest.mark.parametrize("body", ['{"schema_version":99}', "broken", None])
def test_invalid_snapshot_never_requests_build(publish, monkeypatch, body):
    path = Path("data/latest.json")
    if body is None:
        snapshot = json.loads(path.read_text())
        snapshot["sources"] = []
        body = json.dumps(snapshot)
    path.write_text(body)
    monkeypatch.setattr(
        module.urllib.request, "urlopen",
        lambda *a, **kw: pytest.fail("Must not request a build"),
    )
    assert module.main([]) == 1


def test_unknown_only_snapshot_rejected(publish):
    path = Path("data/latest.json")
    snapshot = json.loads(path.read_text())
    for source in snapshot["sources"]:
        source["offers"] = [o for o in source["offers"] if o["sale_unit"] == "unknown"]
    path.write_text(json.dumps(snapshot))
    assert module.main([]) == 1


@pytest.mark.parametrize("hook", ["", "http://api.netlify.com/build_hooks/abc",
                                 "https://example.test/build_hooks/abc"])
def test_missing_or_wrong_hook_rejected(publish, monkeypatch, capsys, hook):
    monkeypatch.setenv("NETLIFY_BUILD_HOOK", hook)
    assert module.main([]) == 1
    assert "repository secret" in capsys.readouterr().err


def test_invalid_commit_never_requests_build(publish, monkeypatch):
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: "master")
    assert module.main([]) == 1


def test_validate_only_never_needs_secret_or_network(publish, monkeypatch):
    monkeypatch.delenv("NETLIFY_BUILD_HOOK")
    monkeypatch.setattr(
        module.urllib.request, "urlopen",
        lambda *a, **kw: pytest.fail("Validation must remain offline"),
    )
    assert module.main(["--validate-only", "data/latest.json"]) == 0
