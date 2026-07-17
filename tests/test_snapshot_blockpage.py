"""A snapshot must not present a bot-wall / challenge page as if it were the
cited source. On 2026-07-14 a Reddit 'Please wait for verification' page was
frozen with a hash and treated as content, which let an assessment stop at a
wall instead of routing through it. The snapshot now DETECTS likely challenge
pages and flags them, so the caller knows to route around rather than quote a
block page as the source."""

from harness.web_snapshot import looks_like_block_page, snapshot_url


def test_known_challenge_markers_are_detected():
    for body in (
        b"Please wait for verification...",
        b"<title>Just a moment...</title> checking your browser",
        b"Enable JavaScript and cookies to continue",
        b"Attention Required! | Cloudflare",
        b"<html><body>Access denied. You have been blocked.</body></html>",
    ):
        assert looks_like_block_page(body, "text/html") is not None


def test_ordinary_content_is_not_flagged():
    body = b"<html><body><h1>Real article</h1><p>" + b"content " * 200 + b"</p></body></html>"
    assert looks_like_block_page(body, "text/html") is None


def test_snapshot_flags_a_block_page_but_still_records_it(tmp_path):
    def fake(url):
        return (200, {"Content-Type": "text/html"},
                b"Please wait for verification. Reddit needs to check.", url)
    doc = snapshot_url("https://www.reddit.com/x", tmp_path, runner=fake)
    # it still freezes the bytes (evidence of the wall), but it is NOT a clean
    # source snapshot: the block is named so a caller routes around it
    assert doc.get("blocked") is True
    assert "block" in doc.get("block_reason", "").lower() or \
        "verification" in doc.get("block_reason", "").lower()
    assert doc["sha256"], "the bytes are still recorded as evidence"


def test_a_truncated_download_is_flagged_not_frozen_as_complete(tmp_path):
    """A response whose body is shorter than its declared Content-Length was
    cut off (early close). Freezing it as a complete archive is a lie; the
    snapshot must flag truncation (tenet 3)."""
    def fake(url):
        return (200, {"Content-Type": "text/html", "Content-Length": "100000"},
                b"<html>only a few hundred bytes arrived before the socket "
                b"closed</html>", url)
    doc = snapshot_url("https://example.org/big", tmp_path, runner=fake)
    assert doc.get("truncated") is True
    assert "100000" in doc.get("truncated_reason", "") or \
        "content-length" in doc.get("truncated_reason", "").lower()
    assert doc["sha256"], "the partial bytes are still recorded as evidence"


def test_a_complete_download_matching_content_length_is_not_flagged(tmp_path):
    body = b"<html>" + b"x" * 500 + b"</html>"
    def fake(url):
        return (200, {"Content-Type": "text/html",
                      "Content-Length": str(len(body))}, body, url)
    doc = snapshot_url("https://example.org/ok", tmp_path, runner=fake)
    assert doc.get("truncated") is not True


def test_a_real_snapshot_is_not_marked_blocked(tmp_path):
    def fake(url):
        return (200, {"Content-Type": "text/html"},
                b"<html><body>" + b"genuine documentation text " * 100 +
                b"</body></html>", url)
    doc = snapshot_url("https://example.org/doc", tmp_path, runner=fake)
    assert doc.get("blocked") is not True
