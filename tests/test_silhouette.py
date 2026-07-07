"""silhouette / inverse-problem falsifier — the shadow that follows, across fields.

One mechanism (reconstruct a hidden object from a lossy projection) across astronomy,
3D rendering, reverse engineering, geometry, systems, dream-state, consciousness. The
honest split: some inverse problems are solvable (shadows collapse to one object),
some have a permanent floor (a coordinate no shadow accesses). Consciousness's
phenomenal residue is flat across every behavioral shadow — the computed SHAPE of the
access/phenomenal gap (an encoded blindness, not a proof about real minds).
"""
from harness.silhouette import run_all, DOMAINS, reconstruction


def test_more_shadows_never_add_ambiguity():
    assert run_all()["all_monotone"] is True


def test_solvable_inverse_problems_collapse_to_one():
    r = run_all()
    assert set(r["solvable"]) == {"trace_recovery", "orthographic", "black_box_id"}
    for res in r["results"]:
        if res["name"] in r["solvable"]:
            assert res["floor"] == 1


def test_underdetermined_have_a_permanent_floor():
    r = run_all()
    assert set(r["underdetermined"]) == {"transit", "visual_hull", "manifest_latent",
                                         "access_vs_phenomenal"}
    for res in r["results"]:
        if res["name"] in r["underdetermined"]:
            assert res["floor"] > 1


def test_consciousness_phenomenal_residue_is_flat_across_behavioral_shadows():
    # the load-bearing honesty: three behavioral probes, phenomenal ambiguity never moves
    res = next(reconstruction(b()) for b in DOMAINS if b.__name__ == "_consciousness")
    focus_amb = [row["focus_ambiguity"] for row in res["curve"]]
    assert focus_amb == [2, 2, 2, 2], "behavioral shadows must NOT shrink the phenomenal residue"
    assert len(res["curve"]) == 4     # baseline + three behavioral probes


def test_honest_note_names_the_encoded_assumption():
    n = run_all()["honest_note"]
    assert "ENCODED" in n and "does not resolve" in n
