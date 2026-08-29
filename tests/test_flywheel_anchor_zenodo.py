"""The Zenodo durability leg: the dry run, then the one gated live deposit.

The DOI is irreversible, so the producer step before it is a dry run that
computes the exact bytes and metadata a deposit would carry and calls nothing;
past it, a single live deposit runs against an injected fake transport, never a
live service. The pure core is tested in test_flywheel_anchor.py, the CLI wiring
in test_flywheel_anchor_cli.py.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
pytest.importorskip("cryptography")

from tests._anchor_fixtures import HEAD, TS, _key, fa  # noqa: E402


# --- the Zenodo durability leg: a dry run before the one live mint ----------
#
# The DOI is irreversible: a published record cannot be unpublished. So the
# producer step before it is a dry run that computes the exact (filename, size,
# bound digest) a deposit WOULD carry and a metadata skeleton to review, and
# calls nothing. It must also refuse a record whose stored digest disagrees with
# its own head here, at the terminal, not at the network, so a corrupt record is
# caught before the operator crosses the live gate.

def test_zenodo_dry_run_reports_the_bound_bytes_and_the_digest():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(anchor_rec)
    assert report["filename"] == "signed-head.json"
    # the deposited bytes are the canonical signed head, and their sha256 IS the
    # record's digest, so the DOI witnesses the same digest the Bitcoin leg does
    from harness.receipt_fields import canonical
    assert report["size_bytes"] == len(canonical(anchor_rec["signed_head"]).encode())
    assert report["bound_digest"] == anchor_rec["anchor_digest"]
    assert report["digest_hex"] == anchor_rec["digest_hex"]
    assert report["metadata"]["metadata"]["title"]        # a fillable skeleton
    assert report["metadata"]["metadata"]["creators"]


def test_zenodo_dry_run_refuses_a_record_whose_digest_disagrees_with_its_head():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    anchor_rec["digest_hex"] = "00" * 32          # no longer matches the head
    with pytest.raises(fa.zenodo_deposit.DepositError):
        fa.zenodo_dry_run(anchor_rec)


def test_zenodo_dry_run_surfaces_the_binding_caveats():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(anchor_rec)
    joined = " ".join(report["does_not_prove"])
    assert "NOT_PROVES_THE_TIMESTAMP" in joined     # a DOI alone orders nothing


def test_zenodo_dry_run_metadata_is_overridable():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(
        anchor_rec, title="Custom title",
        creators=[{"name": "Doe, Jane"}])
    md = report["metadata"]["metadata"]
    assert md["title"] == "Custom title"
    assert md["creators"] == [{"name": "Doe, Jane"}]


def test_cmd_zenodo_is_a_dry_run_and_never_touches_the_network(tmp_path, capsys,
                                                               monkeypatch):
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    path = tmp_path / "anchor.json"
    path.write_text(json.dumps(anchor_rec), encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("a dry run must not reach the deposit client")

    monkeypatch.setattr(fa.zenodo_deposit, "deposit", _boom)
    code = fa.main(["zenodo", "--anchor", str(path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "signed-head.json" in out
    assert anchor_rec["anchor_digest"] in out
    assert "dry run" in out.lower()          # says plainly it minted nothing


def test_cmd_zenodo_refuses_a_corrupt_record_with_a_nonzero_exit(tmp_path, capsys):
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    anchor_rec["digest_hex"] = "00" * 32
    path = tmp_path / "anchor.json"
    path.write_text(json.dumps(anchor_rec), encoding="utf-8")
    code = fa.main(["zenodo", "--anchor", str(path)])
    assert code != 0
    err = capsys.readouterr().err
    assert "REFUSED" in err


# --- the Zenodo live deposit: the one gated step past the dry run ------------
#
# Past the dry run is a single live deposit. It must upload exactly the bound
# bytes the dry run showed, read its token from a file and never from argv or a
# URL, stay a draft unless --publish is given (publish is the one irreversible
# switch), and route a corrupt record to a refusal before any network call. The
# transport is injected, so these run against a fake and never a live service.

class _FakeTransport:
    """Records every call and returns programmed (status, body) replies in order."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None):
        self.calls.append((method, url, dict(headers or {}), body))
        status, payload = self._replies.pop(0)
        if isinstance(payload, (bytes, bytearray)):
            return status, bytes(payload)
        return status, json.dumps(payload).encode()


def _created(dep_id=51, base="https://sandbox.zenodo.org/api"):
    self_url = f"{base}/deposit/depositions/{dep_id}"
    return {"id": dep_id, "links": {
        "self": self_url,
        "bucket": f"{base}/files/bucket-{dep_id}",
        "publish": f"{self_url}/actions/publish"}}


def test_zenodo_live_deposits_exactly_the_bound_bytes_as_a_draft():
    from harness.receipt_fields import canonical
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    want = canonical(rec["signed_head"]).encode()
    ft = _FakeTransport([
        (201, _created()),                    # create
        (201, {"key": "signed-head.json"}),   # upload
        (200, _created()),                    # set metadata
    ])
    result = fa.zenodo_live(rec, ft, token="tok_never_in_url",
                            sandbox=True, publish=False)
    assert result["published"] is False
    assert result["anchor_digest"] == rec["anchor_digest"]
    put = [c for c in ft.calls if c[0] == "PUT" and "/files/" in c[1]]
    assert len(put) == 1 and put[0][3] == want   # the exact canonical head bytes
    for (_m, url, headers, _b) in ft.calls:
        assert "tok_never_in_url" not in url     # never in a URL
        assert headers["Authorization"] == "Bearer tok_never_in_url"


def test_zenodo_live_publish_is_the_one_irreversible_switch():
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    ft = _FakeTransport([
        (201, _created()),
        (201, {"key": "signed-head.json"}),
        (200, _created()),
        (202, {"doi": "10.5281/zenodo.9",
               "links": {"doi": "https://doi.org/10.5281/zenodo.9"}}),
    ])
    result = fa.zenodo_live(rec, ft, token="t", sandbox=True, publish=True)
    assert result["published"] is True
    assert result["doi"] == "10.5281/zenodo.9"
    assert any(c[0] == "POST" and c[1].endswith("/actions/publish")
               for c in ft.calls)


def test_zenodo_live_refuses_a_corrupt_record_before_any_network():
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    rec["digest_hex"] = "00" * 32
    ft = _FakeTransport([])   # any network call pops an empty list and raises
    with pytest.raises(fa.zenodo_deposit.DepositError):
        fa.zenodo_live(rec, ft, token="t", sandbox=True, publish=True)
    assert ft.calls == []     # nothing was sent


def test_cmd_zenodo_live_reads_the_token_from_a_file_and_never_from_argv(
        tmp_path, capsys, monkeypatch):
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    tpath = tmp_path / "sandbox.token"
    tpath.write_text("SECRET_TOKEN_VALUE\n", encoding="utf-8")  # trailing newline stripped
    ft = _FakeTransport([
        (201, _created()),
        (201, {"key": "signed-head.json"}),
        (200, _created()),
    ])
    monkeypatch.setattr(fa.zenodo_deposit, "urllib_transport", ft)
    code = fa.main(["zenodo", "--anchor", str(apath), "--live",
                    "--sandbox", "--token-file", str(tpath)])
    assert code == 0
    assert any(h.get("Authorization") == "Bearer SECRET_TOKEN_VALUE"
               for (_m, _u, h, _b) in ft.calls)     # read from the file
    out = capsys.readouterr().out
    assert "SANDBOX" in out
    assert "SECRET_TOKEN_VALUE" not in out          # the token is never printed


def test_cmd_zenodo_live_refuses_a_missing_token_file(tmp_path, capsys):
    key = _key()
    rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    apath = tmp_path / "anchor.json"
    apath.write_text(json.dumps(rec), encoding="utf-8")
    code = fa.main(["zenodo", "--anchor", str(apath), "--live",
                    "--token-file", str(tmp_path / "nope.token")])
    assert code != 0
    err = capsys.readouterr().err
    assert "token" in err.lower()


def test_read_token_strips_a_utf8_bom(tmp_path):
    # PowerShell's default Out-File writes UTF-8 with a BOM. A BOM is not
    # whitespace, so .strip() leaves it on the token and corrupts the Bearer
    # header. The reader must strip it.
    tpath = tmp_path / "bom.token"
    tpath.write_bytes(b"\xef\xbb\xbfTOKEN_VALUE")   # UTF-8 BOM then the token
    token = fa._read_token(str(tpath))
    assert token == "TOKEN_VALUE"
    assert not token.startswith("﻿")


def test_read_token_funnels_an_unreadable_path_through_deposit_error(tmp_path):
    # A --token-file that is a directory (or otherwise unreadable) must leave
    # through DepositError, the one taxonomy this path uses, not a raw traceback.
    with pytest.raises(fa.zenodo_deposit.DepositError):
        fa._read_token(str(tmp_path))   # a directory, not a file


def test_zenodo_live_report_lines_tolerates_a_none_file_entry():
    # If an upload reply is a 2xx with an empty body, the file key is None. This
    # print runs AFTER a successful publish, so a crash here would hide the DOI
    # and invite a second, duplicate mint. It must not raise.
    result = {"deposition_id": 7, "self_url": "https://zenodo.org/api/x",
              "files": [None], "anchor_digest": "sha256:" + "a" * 64,
              "published": True, "doi": "10.5281/zenodo.7",
              "doi_url": "https://doi.org/10.5281/zenodo.7", "does_not_prove": []}
    lines = fa.zenodo_live_report_lines(result, sandbox=False)
    assert any("10.5281/zenodo.7" in ln for ln in lines)


def test_cmd_zenodo_refuses_publish_without_live(tmp_path, capsys):
    # --publish without --live is a nonsensical combination (a dry run mints
    # nothing). It must be refused, not silently ignored.
    code = fa.main(["zenodo", "--anchor", str(tmp_path / "any.json"), "--publish"])
    assert code != 0
    assert "--live" in capsys.readouterr().err


def test_cmd_zenodo_refuses_a_missing_anchor_file(tmp_path, capsys):
    # A missing or malformed --anchor file must leave through the REFUSED path,
    # not an uncaught traceback.
    code = fa.main(["zenodo", "--anchor", str(tmp_path / "nope.json")])
    assert code != 0
    assert "anchor" in capsys.readouterr().err.lower()
