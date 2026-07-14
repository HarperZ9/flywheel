"""The snapshot fetcher freezes any caller-named URL, and the scaffold now
does that on every message, so it must refuse to be steered at internal or
metadata endpoints. The guard resolves the host and rejects loopback,
private, link-local, and other non-global addresses, by name, before any
connection. And the provenance sidecar must not clobber a prior origin."""

from harness.web_snapshot import _guard_url, snapshot_url


def test_loopback_and_metadata_and_private_are_blocked():
    for url in ("http://127.0.0.1/secret",
                "http://169.254.169.254/latest/meta-data/",
                "http://10.0.0.5/internal",
                "http://192.168.1.1/admin",
                "http://[::1]/x"):
        reason = _guard_url(url)
        assert reason is not None, f"{url} should be blocked"
        assert "not a global address" in reason or "blocked" in reason


def test_non_http_schemes_are_blocked():
    assert _guard_url("file:///etc/passwd") is not None
    assert _guard_url("gopher://127.0.0.1/") is not None


def test_a_global_address_passes_the_guard():
    # numeric IPs resolve locally (no DNS), so this stays offline
    assert _guard_url("http://8.8.8.8/") is None


def test_snapshot_refuses_a_blocked_url_before_fetching():
    doc = snapshot_url("http://169.254.169.254/latest/", "/tmp/should-not-exist")
    assert "error" in doc
    assert "global" in doc["error"] or "blocked" in doc["error"]


def test_injected_runner_still_archives_normally(tmp_path):
    def fake(url):
        return (200, {"Content-Type": "text/html"}, b"<html>ok</html>", url)
    doc = snapshot_url("https://example.org", tmp_path, runner=fake)
    assert doc["sha256"] and "error" not in doc


def test_sidecar_does_not_clobber_a_different_origin(tmp_path):
    body = b"identical bytes served by two urls"

    def fake_a(url):
        return (200, {"Content-Type": "text/plain"}, body, "https://a.example/x")

    def fake_b(url):
        return (200, {"Content-Type": "text/plain"}, body, "https://b.example/y")

    d1 = snapshot_url("https://a.example/x", tmp_path, runner=fake_a)
    d2 = snapshot_url("https://b.example/y", tmp_path, runner=fake_b)
    assert d1["sha256"] == d2["sha256"], "identical bytes, identical hash"
    import json
    sidecar = json.loads(
        (tmp_path / f"{d1['sha256']}.json").read_text(encoding="utf-8"))
    origins = sidecar.get("observed_urls", [])
    assert "https://a.example/x" in origins
    assert "https://b.example/y" in origins, "second origin was clobbered"
