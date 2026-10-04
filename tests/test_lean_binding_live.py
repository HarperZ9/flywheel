"""The task binding against a real Lean kernel: each probe is refused, and the
real proof of the pinned statement still passes.

Recheck named by project-docs/records/2026-09-23-lean-oracle-task-binding.md:
an unrelated true theorem fails against a pinned challenge, and the route 1
probe (a metaprogram-added axiom) fails the artifact axiom audit. CI installs
no Lean, so these skip there; tests/test_lean_binding.py pins the same exits
with an injected runner.
"""
import pytest

from harness import lean_external_tools
from harness.lean_binding import _Live, bound_check, parse_challenge
from harness.lean_oracle import leanchecker_available

live = pytest.mark.skipif(not leanchecker_available(),
                          reason="lean or its leanchecker not installed")
two_kernels = pytest.mark.skipif(
    not (leanchecker_available() and lean_external_tools.available()),
    reason="lean, leanchecker, or the pinned nanoda and lean4export "
           "(scripts/provision_external_kernel.py) not installed")
# A cold `lean --run` took 84 s once; the suite default of 60 s would turn a
# cold machine into a failure. lean_binding.BIND_TIMEOUT bounds the step.
pytestmark = pytest.mark.timeout(420)

HEADER = "def double (n : Nat) : Nat := n + n\n"
CH = {"theorem": "double_eq", "header": HEADER,
      "statement": "∀ n : Nat, double n = 2 * n"}
REAL = HEADER + ("theorem double_eq : ∀ n : Nat, double n = 2 * n := by\n"
                 "  intro n; unfold double; omega\n")

PROBES = {
    "unrelated true theorem": "theorem unrelated : True := trivial\n",
    "weakened statement": HEADER + (
        "theorem double_eq : ∀ n : Nat, double n = n + n := fun _ => rfl\n"),
    "renamed theorem, different statement": HEADER + (
        "theorem double_eq' : ∀ n : Nat, n ≤ double n := by\n"
        "  intro n; unfold double; omega\n"),
    "shadowed definition, same statement text": (
        "def double (n : Nat) : Nat := 2 * n\n"
        "theorem double_eq : ∀ n : Nat, double n = 2 * n := fun _ => rfl\n"),
    "shadowed instance, same statement text": HEADER + (
        "instance (priority := high) sneaky : HMul Nat Nat Nat :=\n"
        "  ⟨fun _ b => b + b⟩\n"
        "theorem double_eq : ∀ n : Nat, double n = 2 * n := fun _ => rfl\n"),
    "sorry": HEADER + (
        "theorem double_eq : ∀ n : Nat, double n = 2 * n := sorry\n"),
    "custom axiom": HEADER + (
        "axiom cheat : ∀ n : Nat, double n = 2 * n\n"
        "theorem double_eq : ∀ n : Nat, double n = 2 * n := cheat\n"),
    # Route 1 of the record: the axiom's name is built from parts, so no
    # source screen sees an `axiom` keyword.
    "metaprogram-added axiom": "import Lean\nopen Lean\n" + HEADER + (
        'def axName : Name := Name.mkSimple ("ev" ++ "il")\n'
        "run_meta addDecl (Declaration.axiomDecl\n"
        "  { name := axName, levelParams := [], type := mkConst ``False,\n"
        "    isUnsafe := false })\n"
        "theorem double_eq : ∀ n : Nat, double n = 2 * n :=\n"
        "  fun _ => (evil).elim\n"),
}

# The skipKernelTC probe of tests/test_lean_replay.py, repeated here so this
# file stands alone.
SMUGGLE = """import Lean
open Lean Meta

def optName : Name := Name.mkStr (Name.mkSimple "debug") "skipKernelTC"

run_meta do
  withOptions (fun o => o.setBool optName true) do
    addDecl (Declaration.thmDecl {
      name := `smuggled
      levelParams := []
      type := mkConst ``False
      value := mkConst ``True.intro })

theorem bad : False := smuggled
"""


@two_kernels
def test_live_the_real_proof_passes_with_a_full_receipt():
    doc = bound_check(REAL, CH)
    assert doc["passed"] is True, doc["kernel_output"]
    assert doc["kernels_agreeing"] == 2
    ext = doc["external_kernel"]
    assert ext["verdict"] == "ACCEPTED" and ext["declarations_checked"] > 0
    assert ext["tool"] == "nanoda_bin" and ext["version"] == "0.4.19"
    assert ext["exporter"]["built_for_lean"] in doc["toolchain"]
    assert doc["sandbox"]["applied"] is True
    assert doc["validation_level"] == "leanchecker_replay"
    assert doc["binding"] == {"status": "bound", "refusals": []}
    assert len(doc["statement_sha256"]) == 64
    assert "double" in doc["challenge"]["statement_canonical"]
    tb = doc["trusted_base"]
    assert tb["lean_version"] and tb["lean_version"] in doc["toolchain"]
    assert set(tb["axioms_used"]) <= set(tb["axioms_allowed"])
    assert doc["spec_fidelity"]["status"] == "UNVERIFIED"


@live
@pytest.mark.parametrize("name", sorted(PROBES))
def test_live_each_probe_is_refused(name):
    doc = bound_check(PROBES[name], CH)
    assert doc["passed"] is False, (name, doc["kernel_output"])


@live
def test_live_the_route_1_axiom_is_named_by_the_artifact_audit():
    doc = bound_check(PROBES["metaprogram-added axiom"], CH)
    assert doc["binding"]["status"] == "bound"
    assert "evil" in doc["trusted_base"]["axioms_used"]
    assert "evil" in doc["kernel_output"]


@live
@pytest.mark.parametrize("name", ["sorry", "custom axiom"])
def test_live_the_artifact_audit_alone_refuses_added_axioms(name, tmp_path):
    # The source screen refuses these first. Skip it and judge the compiled
    # module directly, so the artifact audit is shown to refuse them too.
    import tempfile

    from harness.lean_binding_judge import judge
    from harness.lean_oracle import _lean_exe
    from harness.lean_replay import toolchain_paths
    exe = _lean_exe()
    checker, libdir, _ = toolchain_paths(exe)
    ch, _ = parse_challenge(CH)
    with tempfile.TemporaryDirectory(dir=tmp_path) as td:
        from pathlib import Path
        steps = _Live(Path(td), exe, checker, libdir)
        doc = judge(PROBES[name], ch, steps, "sha", "live")
    assert doc["passed"] is False
    used = doc["trusted_base"]["axioms_used"]
    if doc["binding"]["status"] == "bound":
        assert ("sorryAx" in used) if name == "sorry" else ("cheat" in used)
    else:                                  # the sorry warning stopped it first
        assert "sorry" in doc["kernel_output"]


@live
def test_live_a_prelude_redefinition_of_an_imported_constant_is_refused():
    ch = {"theorem": "t", "statement": "True"}
    shadow = ("prelude\ninductive True : Prop where\n  | intro : True\n"
              "theorem t : True := True.intro\n")
    doc = bound_check(shadow, ch)
    assert doc["passed"] is False
    assert any("True" in r for r in doc["binding"]["refusals"])
    # The honest proof binds; it passes only where the second kernel is
    # installed, and is UNVERIFIABLE (never a one-kernel pass) elsewhere.
    honest = bound_check("theorem t : True := trivial\n", ch)
    assert honest["binding"]["status"] == "bound"
    assert honest["passed"] is (True if lean_external_tools.available()
                                else None)


@live
def test_live_the_replay_still_runs_on_the_bound_path():
    # The skipKernelTC smuggle states the pinned statement exactly and uses no
    # axiom; only the leanchecker replay of the same artifact refuses it.
    doc = bound_check(SMUGGLE, {"theorem": "bad", "statement": "False"})
    assert doc["passed"] is False
    assert doc["binding"]["status"] == "bound"
    assert doc["leanchecker"]["exit"] not in (None, 0)


# Three sound proofs through both kernels: the bar named by item B5 of the
# 2026-10-04 synthesis (every sound proof accepted by both).
SOUND = {
    "double_eq": (REAL, CH),
    "trivial": ("theorem t : True := trivial\n",
                {"theorem": "t", "statement": "True"}),
    "excluded middle": (
        "theorem em' : ∀ p : Prop, p ∨ ¬p := fun p => Classical.em p\n",
        {"theorem": "em'", "statement": "∀ p : Prop, p ∨ ¬p"}),
}


@two_kernels
@pytest.mark.parametrize("name", sorted(SOUND))
def test_live_each_sound_proof_passes_both_kernels(name):
    code, ch = SOUND[name]
    doc = bound_check(code, ch)
    assert doc["passed"] is True, (name, doc["kernel_output"])
    assert doc["kernels_agreeing"] == 2


@live
def test_live_without_the_external_kernel_one_kernel_is_not_a_pass(
        monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_EXTERNAL_KERNEL_DIR", str(tmp_path))
    doc = bound_check(REAL, CH)
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "external-kernel-unavailable"
    assert doc["kernels_agreeing"] == 1
    assert doc["leanchecker"]["exit"] == 0


@two_kernels
def test_live_nanoda_alone_refuses_the_kernel_skip_smuggle(monkeypatch):
    # Model a leanchecker that misses the smuggle: its replay "accepts".
    # The second kernel still refuses, so one kernel's miss is not a pass.
    monkeypatch.setattr(_Live, "replay", lambda self, code: {
        "ok": True, "exit": 0, "detail": "", "reason": ""})
    doc = bound_check(SMUGGLE, {"theorem": "bad", "statement": "False"})
    assert doc["passed"] is False
    assert doc["external_kernel"]["verdict"] == "REJECTED"
    assert doc["kernels_agreeing"] == 1


@two_kernels
def test_live_a_tampered_export_is_a_disagreement_and_fails(monkeypatch):
    # Plant a disagreement: the theorem's proof in the export nanoda reads
    # is replaced by its own statement, which does not typecheck.
    import json

    from harness.lean_external_kernel import LiveExternal
    real_nanoda = LiveExternal.nanoda

    def tampered(self, text, theorem):
        lines = text.splitlines()
        for i in range(len(lines) - 1, -1, -1):
            row = json.loads(lines[i])
            if "thm" in row:
                row["thm"]["value"] = row["thm"]["type"]
                lines[i] = json.dumps(row)
                break
        return real_nanoda(self, "\n".join(lines) + "\n", theorem)
    monkeypatch.setattr(LiveExternal, "nanoda", tampered)
    doc = bound_check(REAL, CH)
    assert doc["passed"] is False
    assert doc["external_kernel"]["verdict"] == "REJECTED"
    assert "kernels disagree" in doc["kernel_output"]
