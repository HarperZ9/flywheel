"""publish_lint contract — the pre-publish gate must catch AND clear.

A gate that never fires and a gate that always fires are equally useless.
These assert both directions: real hazards are caught with the right severity,
and clean product prose passes untouched. The selftest falsifier is exercised
here too, so CI fails if the linter loses its ability to fail.
"""
from harness import publish_lint


def test_selftest_falsifier_passes():
    assert publish_lint.selftest() == 0


def test_secret_is_error():
    hits = publish_lint.scan_text("token = hf_ABCDEFGHIJKLMNOPQRSTUV1234")
    assert any(h["category"] == "SECRETS" and h["severity"] == "error" for h in hits)


def test_interval_less_metric_is_flagged():
    # tenet 4: no claim without its interval. A bare percentage metric on a
    # shipped surface is exactly the claim the credo forbids.
    f = publish_lint.scan_text("Pass@1 is 82.9% on the code-completion suite.")
    assert any(h["rule"] == "claim.nointerval" for h in f)
    ok = publish_lint.scan_text(
        "Pass@1 is 82.9% (95% CI 78.1-86.9) on the code-completion suite.")
    assert not any(h["rule"] == "claim.nointerval" for h in ok)


def test_unmeasured_superlative_is_flagged():
    f = publish_lint.scan_text("The fastest local harness available.")
    assert any(h["rule"] == "claim.superlative" for h in f)
    g = publish_lint.scan_text("This is state-of-the-art tooling.")
    assert any(h["rule"] == "claim.superlative" for h in g)
    # best-of-N is a sampling term, not a superlative claim
    ok = publish_lint.scan_text("a wrapped best-of-5 run")
    assert not any(h["rule"] == "claim.superlative" for h in ok)


def test_forward_slash_windows_path_is_flagged():
    # the repo's own habitual path form must not scan clean
    f = publish_lint.scan_text("See C:/dev/local-model for setup.")
    assert any(h["rule"] == "path.win" for h in f)


def test_local_path_is_error_single_and_escaped():
    single = publish_lint.scan_text(r"see C:\dev\local-model\STATE.md")
    escaped = publish_lint.scan_text(r'{"p": "C:\\dev\\local-model"}')
    assert any(h["category"] == "LOCAL_PATHS" for h in single)
    assert any(h["category"] == "LOCAL_PATHS" for h in escaped)


def test_win_path_matches_once_per_line():
    """The two old overlapping path rules double-counted; one rule now."""
    hits = [h for h in publish_lint.scan_text(r"C:\dev\local-model")
            if h["category"] == "LOCAL_PATHS"]
    assert len(hits) == 1


def test_wsl_and_gitbash_paths_flagged():
    assert any(h["rule"] == "path.wsl"
               for h in publish_lint.scan_text("/mnt/e/local-model-run/x"))
    assert any(h["rule"] == "path.gitbash"
               for h in publish_lint.scan_text("cd /c/dev/local-model"))


def test_dev_register_is_warn():
    hits = publish_lint.scan_text("Status: staged\nawaiting operator approval")
    assert hits and all(h["severity"] == "warn" for h in hits)
    assert {h["category"] for h in hits} == {"DEV_REGISTER"}


def test_stale_claim_is_warn():
    hits = publish_lint.scan_text("No benchmark has been run yet.")
    assert any(h["category"] == "STALE_CLAIM" and h["severity"] == "warn"
               for h in hits)


def test_clean_product_prose_passes():
    clean = ("# Flywheel-Local-Coder-14B\n"
             "A local coding model. Run it in two commands.\n"
             "Pass@1 is 82.9% (95% CI 78.1-86.9) on the 164-task "
             "code-completion suite.\n")
    assert publish_lint.scan_text(clean) == []


def test_receipt_is_deterministic():
    findings = publish_lint.scan_text("token = hf_ABCDEFGHIJKLMNOPQRSTUV1234")
    r1 = publish_lint._receipt(findings, ["a.md"])
    r2 = publish_lint._receipt(findings, ["a.md"])
    assert r1["digest"] == r2["digest"]
    assert r1["error_count"] == 1
