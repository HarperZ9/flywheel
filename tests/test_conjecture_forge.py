"""Generation under witness: the forge PROPOSES conjectures, the kernel is
the sole judge, and novelty is corpus-relative and hashed, so the forge
never re-proposes what the corpus already holds. A refused conjecture is
recorded as refused, never stored, never narrated into a claim."""

from harness.conjecture_forge import (enumerate_conjectures, forge_round,
                                      grade_novelty, normalize_statement)


def _grid_kernel(code: str) -> dict:
    """Test double for the Lean kernel: evaluates both sides on a grid of
    Nat values. Exact for the forge's grammar (linear, and no reachable
    subtraction ever truncates), so acceptance means the identity holds
    and refusal means a countermodel exists on the grid."""
    import re
    m = re.search(r"\)\s*:\s*(.+?)\s*=\s*(.+?)\s*:=", code)
    if not m:
        return {"passed": False, "kernel_output": "unparseable"}
    lhs, rhs = m.group(1), m.group(2)
    try:
        ok = all(eval(lhs, {"min": min, "max": max}, {"n": n, "m": mm})
                 == eval(rhs, {"min": min, "max": max}, {"n": n, "m": mm})
                 for n in range(7) for mm in range(7))
    except Exception:
        return {"passed": False, "kernel_output": "unevaluable"}
    return {"passed": ok, "toolchain": "injected",
            "kernel_output": "ok" if ok else "countermodel on grid"}


def test_enumeration_is_deterministic_and_distinct():
    a = enumerate_conjectures(24)
    b = enumerate_conjectures(24)
    assert a == b
    assert len(set(a)) == 24
    assert all(s.startswith("theorem ") and ":= by" in s for s in a)


def test_enumeration_offset_continues_not_repeats():
    first = enumerate_conjectures(10)
    rest = enumerate_conjectures(10, offset=10)
    assert not set(first) & set(rest)


def test_normalization_is_alpha_and_name_invariant():
    s1 = "theorem cj_a (n m : Nat) : n + m = m + n := by omega"
    s2 = "theorem cj_b (x y : Nat) : x + y = y + x := by omega"
    s3 = "theorem cj_c (n m : Nat) : n + m = m + m := by omega"
    assert normalize_statement(s1) == normalize_statement(s2)
    assert normalize_statement(s1) != normalize_statement(s3)


def test_forge_round_survivors_carry_kernel_receipts(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    art = forge_round(24, kernel=_grid_kernel)
    assert art["schema"] == "flywheel.conjecture-forge/v2"
    assert art["proposed"] == 24
    assert art["accepted"], "the grid kernel must accept true identities"
    assert art["proposed"] == len(art["accepted"]) + art["refused"]
    for s in art["accepted"]:
        assert s["verdict"]["passed"] is True
        assert s["statement_sha256"]
    # refused conjectures never enter the store
    from harness.store import query_entities
    assert len(query_entities(kind="theorem")) == len(art["accepted"])


def test_second_round_never_reproposes_the_corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    r1 = forge_round(12, kernel=_grid_kernel)
    r2 = forge_round(12, kernel=_grid_kernel)
    h1 = {s["statement_sha256"] for s in r1["accepted"]}
    h2 = {s["statement_sha256"] for s in r2["accepted"]}
    assert not h1 & h2, "novelty is corpus-relative: no re-proposal"
    assert r2["corpus_size"] >= len(r1["accepted"])


def test_forge_survivors_land_on_rung_L1(tmp_path, monkeypatch):
    """Forge survivors are corpus-absent by construction and closed by the
    cheap tactic: rung L1, never L2. Cheap-closable is not deep."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    art = forge_round(24, kernel=_grid_kernel)
    assert all(s["rung"] == "L1" for s in art["accepted"])


def test_ladder_grades_corpus_present_as_L0(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    r1 = forge_round(12, kernel=_grid_kernel)
    held = r1["accepted"][0]["statement"]
    g = grade_novelty(held, kernel=_grid_kernel)
    assert g["rung"] == "L0", "already in the corpus: proved but not novel"


def test_ladder_grades_L2_only_with_a_strong_proof(tmp_path, monkeypatch):
    """L2 means the cheap ladder could NOT close it but a supplied strong
    proof did. Without the strong proof it is just refused."""
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))

    def cheap_refuses_strong_passes(code):
        return {"passed": "by strong" in code, "toolchain": "injected"}

    stmt = "theorem cj_d (n m : Nat) : n * m = m * n := by omega"
    strong = "theorem cj_d (n m : Nat) : n * m = m * n := by strong"
    g = grade_novelty(stmt, kernel=cheap_refuses_strong_passes,
                      strong_proof=strong)
    assert g["rung"] == "L2"
    g2 = grade_novelty(stmt, kernel=cheap_refuses_strong_passes)
    assert g2["rung"] == "refused"


def test_declared_kernel_yields_no_survivors_no_claims(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    art = forge_round(6, kernel=lambda code: {"passed": None,
                                              "kernel_output": "no toolchain"})
    assert art["accepted"] == []
    assert art["declared"] == 6
    from harness.store import query_entities
    assert query_entities(kind="theorem") == []


def test_l2_requires_the_strong_proof_to_prove_the_same_proposition():
    """grade_novelty must not grant L2 from an UNRELATED strong proof: a
    false conjecture cannot earn the deepest rung because some other true
    theorem was proved (tenet 2, accept-a-wrong-thing)."""
    false_stmt = "theorem cj_x (n m : Nat) : n + m = n := by omega"   # false
    unrelated = "theorem t : True := by trivial"                      # true, other prop
    def kern(code):
        # cheap tactic fails on the false stmt; the unrelated proof passes
        return {"passed": ("True" in code)}
    g = grade_novelty(false_stmt, kernel=kern, strong_proof=unrelated)
    assert g["rung"] != "L2", "an unrelated strong proof must not grant L2"
    assert g["rung"] == "refused"
