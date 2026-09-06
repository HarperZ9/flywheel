"""The code-scan surface, through the handler and over the wire.

`test_vulnerability_scan.py` covers the rules and the seals. What is left
is the part a caller touches, and the two things the route refuses: a tree
it was not asked to serve, and a suppression carried in the request body.
Both refusals are about what a caller may choose. A scan route that takes
a path is a file-read primitive wearing a security name, and a body-borne
suppression quiets a finding without leaving a record anybody reviews.

The last test goes through `gateway._Handler` rather than calling the
handler directly, because the parity row for this capability cites the
route, and a handler nothing dispatches to is the failure that witness
rule was written to catch.
"""
import io
import json

import pytest

from harness import scan_route as sr
from harness.scan_route import (handle_scan_get, handle_scan_post,
                                suppressions_path)
from harness.vulnerability_scan import load_scans, scans_path

PATH = "/api/scan/vulnerabilities"
NOW = "2026-09-06T18:00:00Z"

SHELL_SRC = """
import subprocess


def go(cmd):
    subprocess.run(cmd, shell=True)
"""

CLEAN_SRC = """
import subprocess


def go(cmd):
    return subprocess.run(["echo", cmd], check=True)
"""


def _clock(stamp=NOW):
    return lambda: stamp


def _repo(tmp_path, **files):
    base = tmp_path / "repo" / "harness"
    base.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (base / f"{name}.py").write_text(text, encoding="utf-8")
    return tmp_path / "repo"


def _run(tmp_path):
    return tmp_path / "run"


def _post(tmp_path, body=None, **kw):
    return handle_scan_post(PATH, body or {}, root=_repo(tmp_path),
                            run_root=_run(tmp_path), clock=_clock(), **kw)


def _get(tmp_path):
    return handle_scan_get(PATH, root=_repo(tmp_path),
                           run_root=_run(tmp_path), clock=_clock())


def _suppress(tmp_path, rows):
    path = suppressions_path(_run(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


def test_a_post_scans_appends_and_hands_back_a_re_checkable_record(tmp_path):
    _repo(tmp_path, shell=SHELL_SRC)
    body, code = _post(tmp_path)
    assert code == 200 and body["scanned"] is True
    assert body["scan"]["counts"]["high"] == 1
    assert body["scan"]["clean"] is False
    assert body["verify"] == {"record_sealed": True, "corpus_matches": True,
                              "ruleset_matches": True}
    assert len(load_scans(scans_path(_run(tmp_path)))) == 1


def test_a_get_before_any_scan_says_so_rather_than_inventing_one(tmp_path):
    body, code = _get(tmp_path)
    assert code == 200 and body["scans"] == 0
    assert body["latest"] is None and body["verify"] is None
    assert body["chain_intact"] is True and body["head_sha256"] == ""


def test_a_get_reports_the_last_scan_with_both_verdicts(tmp_path):
    _repo(tmp_path, ok=CLEAN_SRC)
    _post(tmp_path)
    body, code = _get(tmp_path)
    assert code == 200 and body["scans"] == 1
    assert body["latest"]["clean"] is True
    assert body["chain_intact"] is True
    assert body["head_sha256"] == body["latest"]["scan_sha256"]
    assert body["verify"]["corpus_matches"] is True


def test_the_second_scan_cites_the_first(tmp_path):
    _repo(tmp_path, ok=CLEAN_SRC)
    first, _ = _post(tmp_path)
    second, _ = _post(tmp_path)
    assert second["scan"]["prev_sha256"] == first["scan"]["scan_sha256"]
    body, _ = _get(tmp_path)
    assert body["scans"] == 2 and body["chain_intact"] is True


def test_a_verify_that_no_longer_matches_the_tree_says_which_half_moved(
        tmp_path):
    root = _repo(tmp_path, ok=CLEAN_SRC)
    _post(tmp_path)
    (root / "harness" / "ok.py").write_text(SHELL_SRC, encoding="utf-8")
    body, _ = _get(tmp_path)
    # The stored record is still sound. It describes a tree nobody has now.
    assert body["verify"]["record_sealed"] is True
    assert body["verify"]["corpus_matches"] is False
    assert body["chain_intact"] is True


def test_a_scan_onto_a_broken_chain_refuses_rather_than_burying_it(tmp_path):
    """Fail closed, the same way a tick onto a broken fire chain does.

    Appending a clean scan on top of a tampered history would put the
    reassuring record exactly where the break is hardest to notice.
    """
    _repo(tmp_path, shell=SHELL_SRC)
    body, _ = _post(tmp_path)
    assert body["scan"]["clean"] is False
    path = scans_path(_run(tmp_path))
    records = json.loads(path.read_text(encoding="utf-8"))
    records[0]["clean"] = True            # the edit somebody would make
    path.write_text(json.dumps(records), encoding="utf-8")
    body, code = _post(tmp_path)
    assert code == 409 and body["scanned"] is False
    assert "broken" in body["refused"]
    roster, _ = _get(tmp_path)
    assert roster["chain_intact"] is False


def test_the_route_scans_named_trees_and_nothing_else(tmp_path):
    _repo(tmp_path, ok=CLEAN_SRC)
    body, code = _post(tmp_path, {"trees": ["harness"]})
    assert code == 200 and body["scan"]["trees"] == ["harness"]
    body, code = _post(tmp_path, {"trees": ["../../etc"]})
    assert code == 422 and body["error"]["code"] == "INVALID_REQUEST"
    body, code = _post(tmp_path, {"trees": []})
    assert code == 422


def test_the_scanned_tree_is_not_a_field_a_caller_can_set(tmp_path):
    """A root in the body would make this a file-read primitive.

    The request is honoured for which named trees to cover and ignored on
    where they live, so a caller cannot point the scanner somewhere else.
    """
    elsewhere = tmp_path / "elsewhere" / "harness"
    elsewhere.mkdir(parents=True)
    (elsewhere / "shell.py").write_text(SHELL_SRC, encoding="utf-8")
    _repo(tmp_path, ok=CLEAN_SRC)
    body, code = _post(tmp_path, {"root": str(tmp_path / "elsewhere"),
                                  "path": str(elsewhere)})
    assert code == 200 and body["scan"]["clean"] is True
    assert body["scan"]["files_in_corpus"] == 1


def test_suppressions_come_from_the_file_and_never_from_the_body(tmp_path):
    _repo(tmp_path, shell=SHELL_SRC)
    body, _ = _post(tmp_path, {"suppressions": [
        {"rule_id": "shell-true", "path": "harness/shell.py",
         "reason": "asked for in a request nobody reviews"}]})
    assert body["scan"]["counts"]["high"] == 1
    assert body["scan"]["suppressed_count"] == 0
    _suppress(tmp_path, [{"rule_id": "shell-true", "path": "harness/shell.py",
                          "reason": "reviewed and accepted on the sixth"}])
    body, _ = _post(tmp_path)
    assert body["scan"]["counts"]["high"] == 0
    assert body["scan"]["suppressed_count"] == 1


def test_a_broken_suppression_file_is_refused_not_read_as_none(tmp_path):
    """A file somebody wrote and broke would otherwise scan stricter.

    The findings it was meant to excuse would arrive as a regression with
    no trace back to the typo that caused it.
    """
    _repo(tmp_path, shell=SHELL_SRC)
    path = suppressions_path(_run(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[{not json", encoding="utf-8")
    body, code = _post(tmp_path)
    assert code == 422 and body["error"]["code"] == "INVALID_REQUEST"
    _suppress(tmp_path, {"rule_id": "shell-true"})
    body, code = _post(tmp_path)
    assert code == 422 and "not a list" in body["error"]["message"]


def test_a_suppression_naming_a_rule_that_does_not_exist_is_refused(tmp_path):
    _repo(tmp_path, shell=SHELL_SRC)
    _suppress(tmp_path, [{"rule_id": "shell-tru", "path": "harness/shell.py",
                          "reason": "a typo that covers nothing"}])
    body, code = _post(tmp_path)
    assert code == 422 and "unknown rule" in body["error"]["message"]


def test_the_cap_shortens_the_list_and_never_the_count(tmp_path,
                                                       monkeypatch):
    monkeypatch.setattr(sr, "FINDINGS_SHOWN", 1)
    _repo(tmp_path, shell=SHELL_SRC, more=SHELL_SRC)
    body, _ = _post(tmp_path)
    assert len(body["scan"]["findings"]) == 1
    assert body["scan"]["findings_total"] == 2
    assert body["scan"]["findings_truncated"] == 1
    assert body["scan"]["counts"]["high"] == 2


def test_an_unknown_scan_route_is_a_404(tmp_path):
    _, code = handle_scan_get("/api/scan", root=_repo(tmp_path),
                              run_root=_run(tmp_path), clock=_clock())
    assert code == 404
    _, code = handle_scan_post("/api/scan/purge", {}, root=_repo(tmp_path),
                               run_root=_run(tmp_path), clock=_clock())
    assert code == 404


class _FakeHeaders:
    def __init__(self, n):
        self._n = n

    def get(self, k, d=None):
        return self._n if k == "Content-Length" else d


def _handler(path, tmp_path, monkeypatch):
    import harness.gateway as gateway
    monkeypatch.setattr(gateway._Handler, "root", _repo(tmp_path))
    monkeypatch.setattr(gateway._Handler, "run_root", str(_run(tmp_path)))
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW)
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    return h


def test_the_gateway_dispatches_both_scan_verbs(tmp_path, monkeypatch):
    _repo(tmp_path, shell=SHELL_SRC)
    raw = json.dumps({"trees": ["harness"]}).encode()
    post = _handler(PATH, tmp_path, monkeypatch)
    post.headers = _FakeHeaders(str(len(raw)))
    post.rfile = io.BytesIO(raw)
    sent = {}
    post._json = lambda b, code=200: sent.update(body=b, code=code)
    post._post()
    assert sent["code"] == 200 and sent["body"]["scanned"] is True
    assert sent["body"]["scan"]["counts"]["high"] == 1

    get = _handler(PATH, tmp_path, monkeypatch)
    get.headers = _FakeHeaders("0")
    seen = {}
    get._json = lambda b, code=200: seen.update(body=b, code=code)
    get._get()
    assert seen["code"] == 200 and seen["body"]["scans"] == 1
    assert seen["body"]["chain_intact"] is True


@pytest.mark.parametrize("payload", ["", "not json at all"])
def test_a_body_that_is_not_json_is_treated_as_an_empty_request(
        tmp_path, monkeypatch, payload):
    _repo(tmp_path, ok=CLEAN_SRC)
    raw = payload.encode()
    h = _handler(PATH, tmp_path, monkeypatch)
    h.headers = _FakeHeaders(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    assert sent["code"] == 200 and sent["body"]["scanned"] is True
