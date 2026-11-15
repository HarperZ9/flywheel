"""With no project config and no domain profile, command output is byte-identical
to the release line before project rules, domain profiles, allow-change and the
change report were added. The pins were computed from that release line
(commit b9eaae6) on corpus/ai/blog-intro.md copied to an empty directory.

fix_none was re-pinned when `fix --backend none` gained the closed-list phrase
edits (tests/test_fix_none.py). Its output now lists those edits, and the sample
loses one sentence-initial "Moreover,". fix_none and plan were re-pinned when the
editor receipt and the plan named their limit field scope (editor-receipt/v2)."""
import contextlib
import hashlib
import io
import json
import os
import shutil

import pytest

import articulate
from articulate import cli, host_edit, receipt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "corpus", "ai", "blog-intro.md")

PINS = {
    "check_json": (["check", "sample.md", "--json"],
                   "992563714272db38dfa2d2654443d049c2d60f632bff3fc93323c360b2c83f9c"),
    "check_spans_json": (["check", "sample.md", "--json", "--spans"],
                         "3af53dfdde834b492d424b57c5c7e9d2d5237c4e589f1795c14a432889ceeced"),
    "check_text": (["check", "sample.md", "--verbose"],
                   "50ef2198e62d2d172351ad4b4815935d17a45269dbe6b99a3bfabb7507fea6c2"),
    "score": (["score", "sample.md"],
              "9e2e2f2a452c8b305e96925f9936db8c5c614c9b7b7703e5de92645c6ab9871c"),
    "fix_none": (["fix", "sample.md", "--backend", "none"],
                 "818b57eb59be9e9beaa3019398d97040f43d905210172c6ea69db9db103e3790"),
    "plan": (["plan", "sample.md"],
             "8ed4140984c41fb5f1dfc5ba9a3085c28866e582e87f1b2c96d78b29b22a33b8"),
}
RECEIPT_CLI = "05a6137b8713b3b6dfbef88a8dce695a7f57cede46053999b12c8499cc7c9dfb"
RECEIPT_LIB = "8859f89cacdf7c637a73c8e724c3b738d9de412e0ac63fee7f0b079d53160a24"
PLAN_ID = "f924d6e7db3f3c4b3c23e38a31bf0c2ee15686ff2f7fdd849bea51c3b00fbc28"


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _at_pinned_version(rec):
    # A receipt names the package version, which moves with every release. The
    # pins were taken at 0.8.0, so compare everything else byte for byte.
    assert rec["articulate_version"] == articulate.__version__
    return dict(rec, articulate_version="0.8.0")


def _run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc, buf.getvalue()


@pytest.fixture
def sample_dir(tmp_path, monkeypatch):
    # The CLI fills a receipt's reviewer from GITHUB_ACTOR, which CI sets.
    monkeypatch.delenv("GITHUB_ACTOR", raising=False)
    shutil.copy(SAMPLE, tmp_path / "sample.md")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("name", sorted(PINS))
def test_command_output_is_unchanged(sample_dir, name):
    argv, digest = PINS[name]
    rc, out = _run(argv)
    assert rc == 0
    assert _sha(out) == digest, name


def test_cli_receipt_is_unchanged(sample_dir):
    rc, out = _run(["receipt", "sample.md", "--spans"])
    rec = json.loads(out)
    rec.pop("created_at")
    assert rc == 0 and _sha(json.dumps(_at_pinned_version(rec), sort_keys=True)) == RECEIPT_CLI
    assert not {"project_rules", "extension_fingerprint"} & set(rec)


def test_library_receipt_and_plan_id_are_unchanged(sample_dir):
    text = open("sample.md", encoding="utf-8").read()
    rec = receipt.make_receipt(text, None, per_span=True, created_at="2026-01-01T00:00:00+00:00")
    assert _sha(json.dumps(_at_pinned_version(rec), sort_keys=True)) == RECEIPT_LIB
    assert receipt.verify_receipt(rec, text)[0] == "Match"
    assert _sha(host_edit.edit_plan(text)["plan_id"]) == PLAN_ID
