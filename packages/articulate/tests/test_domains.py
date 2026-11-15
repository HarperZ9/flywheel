"""Domain profiles: register profiles plus rule packs, run outside the detector."""
import contextlib
import io
import json
import os

import pytest

from articulate import (bench, checkext, cli, detector, domains, host_edit, lsp_server,
                        profiles, receipt, rules_ext)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UX = open(os.path.join(ROOT, "corpus", "domains", "ux-microcopy", "flagged.txt"),
          encoding="utf-8").read()
REVIEW = open(os.path.join(ROOT, "corpus", "domains", "code-review", "flagged.md"),
              encoding="utf-8").read()


def _cats(result, tier=None):
    keys = [tier] if tier else ["high", "medium", "low"]
    return {f["category"] for k in keys for f in result[k]}


def test_every_domain_profile_names_its_base_and_packs():
    assert domains.names() == ["author-voice", "chat", "code-review", "controlled-english", "note", "outbound",
                               "plain-language", "product-copy", "publication", "rfc-keywords",
                               "ux-microcopy"]
    for name in domains.names():
        prof = domains.load_profile(name)
        assert prof["domain"] == name and prof["rule_packs"]
        assert set(prof["rule_packs"]) <= set(rules_ext.PACKS)
    assert domains.load_profile("rfc-keywords")["keep"] == profiles.load("normative-spec")["keep"]
    assert domains.load_profile("ux-microcopy")["slop"] == "strict"


def test_no_rule_packs_returns_the_detector_result_unchanged():
    for name in ("flavored", "normative-spec", "essay"):
        prof = profiles.load(name)
        assert checkext.check_text(UX, profile=prof) == detector.check_text(UX, profile=prof)


def test_pack_findings_gate_under_strict_and_keep_the_texture_score():
    prof = domains.load_profile("ux-microcopy")
    base = detector.check_text(UX, profile=prof)
    r = checkext.check_text(UX, profile=prof)
    assert "ux-length" in _cats(r, "medium")
    assert r["gate"] == "blocked" and base["gate"] == "ok"
    assert r["blocking_count"] == len(r["high"]) + len(r["medium"])
    assert r["texture_score"] == base["texture_score"] and r["verdict"] == "flagged"


def test_flavored_domain_reports_medium_pack_findings_without_blocking():
    r = checkext.check_text(REVIEW, profile=domains.load_profile("code-review"))
    assert "review-absolute" in _cats(r, "medium")
    assert r["gate"] == "ok" and r["blocking_count"] == 0 and r["clean"] is False


def test_gate_promote_reaches_pack_categories():
    prof = dict(domains.load_profile("code-review"), gate_promote=("review-no-reason",))
    r = checkext.check_text(REVIEW, profile=prof)
    assert r["gate"] == "blocked"
    assert r["blocking_count"] == len(r["high"]) + sum(
        1 for f in r["low"] if f["category"] == "review-no-reason")


def test_short_text_with_only_a_low_pack_finding_is_not_unverifiable():
    prof = domains.load_profile("code-review")
    text = "Just rename it.\n"
    assert detector.check_text(text, profile=prof)["verdict"] == "unverifiable"
    r = checkext.check_text(text, profile=prof)
    assert r["low"] and r["verdict"] == "clean"


def test_unknown_profile_lists_domain_profiles():
    with pytest.raises(profiles.ProfileError, match="domain profiles: author-voice, chat, code-review"):
        domains.load_profile("no-such-profile")


def _run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(argv)
    return rc, buf.getvalue()


def test_cli_check_resolves_domain_names_and_tags(tmp_path):
    path = tmp_path / "strings.txt"
    path.write_text(UX, encoding="utf-8")
    rc, out = _run(["check", str(path), "--profile", "ux-microcopy", "--json", "--gate"])
    res = json.loads(out)["results"][0]
    assert rc == 1 and res["profile"] == "ux-microcopy" and "ux-length" in _cats(res)
    path.write_text("<!-- writing-profile: ux-microcopy -->\n" + UX, encoding="utf-8")
    rc, out = _run(["check", str(path), "--json"])
    assert json.loads(out)["results"][0]["profile"] == "ux-microcopy"


def test_cli_spans_and_sarif_carry_pack_findings(tmp_path):
    path = tmp_path / "review.md"
    path.write_text(REVIEW, encoding="utf-8")
    rc, out = _run(["check", str(path), "--profile", "code-review", "--json", "--spans"])
    blocks = json.loads(out)["results"][0]["blocks"]
    assert "review-absolute" in _cats(blocks[2])
    rc, out = _run(["check", str(path), "--profile", "code-review", "--sarif"])
    rules = {r["ruleId"] for r in json.loads(out)["runs"][0]["results"]}
    assert any(rid.startswith("review-absolute/") for rid in rules)


def test_receipt_records_domain_and_extension_fingerprint(monkeypatch):
    rec = receipt.make_receipt(UX, "ux-microcopy", per_span=True)
    assert rec["profile"] == "ux-microcopy" and rec["gate"] == "blocked"
    assert rec["extension_fingerprint"] == rules_ext.fingerprint()
    assert receipt.verify_receipt(rec, UX)[0] == "Match"
    stripped = {k: v for k, v in rec.items() if k != "extension_fingerprint"}
    assert receipt.verify_receipt(stripped, UX)[0] == "Unverifiable"
    monkeypatch.setattr(rules_ext, "fingerprint", lambda: "sha256:changedpacks0000")
    verdict, detail = receipt.verify_receipt(rec, UX)
    assert verdict == "Unverifiable" and "rule packs changed" in detail


def test_plain_receipt_with_an_extension_field_is_unverifiable():
    rec = receipt.make_receipt(UX, "flavored")
    assert "extension_fingerprint" not in rec
    rec["extension_fingerprint"] = rules_ext.fingerprint()
    assert receipt.verify_receipt(rec, UX)[0] == "Unverifiable"


def test_extension_fingerprint_moves_with_a_pack_option(monkeypatch):
    before = rules_ext.fingerprint()
    monkeypatch.setitem(rules_ext.PACKS["plain-language"].OPTIONS, "max_grade", 6.0)
    assert rules_ext.fingerprint() != before


def test_lsp_diagnostics_use_domain_profiles():
    diags = lsp_server.build_diagnostics(UX, "file:///C:/tmp/strings.txt", "ux-microcopy")
    assert any(d["code"].startswith("ux-length/") for d in diags)
    tagged = "<!-- writing-profile: ux-microcopy -->\n" + UX
    assert any(d["code"].startswith("ux-") for d in
               lsp_server.build_diagnostics(tagged, "file:///C:/tmp/strings.txt"))


def test_edit_plan_binds_the_domain_profile_and_its_findings():
    plan = host_edit.edit_plan(UX, profile="ux-microcopy")
    assert plan["profile"]["rule_packs"] == ["ux-microcopy"]
    assert any(f["category"] == "ux-length" for f in plan["findings_before"])
    assert plan["gate_before"] == "blocked"
    settings = host_edit.plan_settings(UX, plan["plan_id"])
    assert settings["profile"]["domain"] == "ux-microcopy"


def test_bench_runs_the_domain_corpus(capsys):
    misses = bench.main([os.path.join(ROOT, "corpus")])
    out = capsys.readouterr().out
    assert "[bench-domains] samples 24, mismatches 0" in out
    assert misses == 0
