"""cross-domain criterion-conservation falsifier — one asymmetry, seven unconnected fields.

The transpile-conservation principle (conserve the criterion, not the bits) recurs in
finance, music, color science, formal grammar, geometry, dimensional physics, and
sorting. In each: a faithful transform conserves the invariant, a cheat breaks it, and
a weak surface check misses the cheat the criterion catches. HONEST: this is reach
(the lens applies to any domain with a computable invariant), not a discovered law.
"""
from harness.cross_domain import run_all, run_domain, DOMAINS


def test_asymmetry_holds_across_every_unconnected_field():
    r = run_all()
    assert r["coverage"] == 1.0, f"the asymmetry must hold in every field: {r['per_domain']}"
    assert len(r["fields"]) == 7, "seven genuinely different fields"


def test_each_domain_conserves_faithful_breaks_cheat_and_surface_misses():
    for d in DOMAINS:
        p = run_domain(d)
        assert p["faithful_conserves"], f"{d.name}: faithful transform must conserve the criterion"
        assert p["cheat_breaks"], f"{d.name}: cheat must break the criterion"
        assert p["surface_misses_cheat"], f"{d.name}: surface check must miss what the criterion catches"


def test_honest_framing_is_present():
    # the module must carry the anti-apophenia caveat, not sell convergence as proof
    assert "expected" in run_all()["honest_note"] and "not a discovered law" in run_all()["honest_note"]
