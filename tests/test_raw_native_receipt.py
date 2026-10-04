"""raw-native's own receipt.json (0.5.0), read directly and held to its files.

Claims under test:
- the receipts the 0.5.0 Windows and Linux binaries wrote seal under the
  vendored contract and agree with their files and certificate, and level 1
  reports them in its receipt;
- a receipt whose tolerance verdict was flipped and then resealed seals fine
  but disagrees with the certificate, so level 1 fails;
- a receipt whose content hash points at the ray-traced AO instead of the
  screen-space AO fails, and so does an edited, unsealed receipt;
- a render without a receipt (raw-native 0.4.0) still passes level 1;
- paired mutation: a check that skips the agreement step passes the resealed
  forgery, which the forgery test catches.
"""
from __future__ import annotations

import json

import pytest

from harness._vendor import superstack as ss
from harness.certificates import raw_ao, raw_ao_receipt as rr, raw_native_receipt as rn
from tests.raw_native_fixtures import cert, files

NAME = "windows-x64"


def _with_receipt(edit, seal: bool = True) -> dict:
    fs = files(NAME)
    rec = json.loads(fs[rn.NAME])
    edit(rec)
    fs[rn.NAME] = json.dumps(ss.seal(rec) if seal else rec).encode()
    return fs


@pytest.mark.parametrize("name", ["windows-x64", "linux-x64", "windows-x64-refuted"])
def test_each_release_receipt_seals_and_agrees(name):
    found = rn.check(cert(name), files(name))
    assert found["present"] and found["errors"] == []
    summary = rr.level1_receipt(cert(name), files(name))["flywheel"]["native_receipt"]
    assert summary["agrees"] is True and summary["identity"] == "DRIFT"


def _forgery_known_answer() -> None:
    fs = _with_receipt(lambda r: r["reconcile"]["tolerance"].update(verdict="refuted"))
    found = rn.check(cert(NAME), fs)
    assert "superstack:seal" not in found["errors"]
    assert found["errors"] == ["tolerance verdict is not the certificate's"]
    result = raw_ao.level1(cert(NAME), fs)
    assert result["verdict"] == "FAIL"


def test_a_resealed_forgery_fails_on_agreement():
    _forgery_known_answer()


def test_a_receipt_about_the_wrong_buffer_fails():
    fs = _with_receipt(lambda r: r.update(content_sha256=r["reconcile"]["reference"]
                                          ["content_sha256"]))
    assert "content is not ao_ss" in rn.check(cert(NAME), fs)["errors"]


def test_an_edited_unsealed_receipt_fails_its_seal():
    fs = _with_receipt(lambda r: r["outputs"].update({"mask.pgm": "0" * 64}), seal=False)
    errors = rn.check(cert(NAME), fs)["errors"]
    assert "superstack:seal" in errors and "output mask.pgm" in errors


def test_a_render_without_a_receipt_still_passes():
    fs = files(NAME)
    del fs[rn.NAME]
    result = raw_ao.level1(cert(NAME), fs)
    assert result["verdict"] == "PASS" and result["native_receipt"]["present"] is False


def test_paired_mutation_skipping_the_agreement_step_is_caught(monkeypatch):
    monkeypatch.setattr(rn, "_agreement", lambda rec, c, fs: [])
    with pytest.raises(AssertionError):
        _forgery_known_answer()
