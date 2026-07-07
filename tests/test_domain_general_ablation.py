"""domain-general externalization falsifier — the honest 'covers every domain'.

There is no domain-spanning MAGNITUDE (the capstone retired that). But the
externalization FORM is universal, and this proves it by demonstration, not
assertion: across distinct domains (arithmetic, selection, predicate, transform,
counting), a non-self-authored check catches the cheat the self-authored one
accepts, with the refutation executing in every one.
"""
from harness.externalization_ablation import run_all_domains, DOMAINS


def test_externalization_form_covers_every_domain(tmp_path):
    r = run_all_domains(tmp_path)
    assert r["coverage"] == 1.0, f"the form must catch the cheat in EVERY domain: {r['per_domain']}"
    assert r["caught"] == r["n_domains"] == len(DOMAINS)
    assert r["all_refutations_executed"] is True
    # per-domain: self-authored accepts the cheat, external refutes it
    for p in r["per_domain"]:
        assert p["self_authored_verdict"] == "PASS" and p["external_verdict"] == "FAIL"
