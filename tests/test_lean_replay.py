"""The leanchecker rung: a declaration stored without a kernel check is refused.

The probe below proves False on Lean 4.34.0. A metaprogram adds `smuggled`
with `debug.skipKernelTC` switched on, spelling the option as a `Name` built
from parts so the hygiene regex never sees it. `lean` exits 0 with no
warning and `#print axioms bad` reports no axioms, so before the replay rung
the oracle returned passed=True with footprint {"bad": []} (reproduced
2026-09-23 against 91dfd406d). leanchecker replays the compiled module in a
fresh process and refuses `smuggled`.

The unit tests inject the runner, so they need no toolchain. The live tests
run only where `lean` is installed and its toolchain ships leanchecker; a
toolchain without it gives UNVERIFIABLE by design, so they skip there.
"""
import pytest

from harness import lean_replay
from harness.lean_oracle import (LeanOracle, _lean_exe, lean_check,
                                 leanchecker_available)

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
CONTROL = "theorem good : 2 + 2 = 4 := rfl\n"

# A metaprogram writes a bogus `Init` package into the build directory the
# oracle compiles into. With the build directory first on LEAN_PATH that
# plant shadowed the real `Init`; the toolchain library goes first instead.
PLANT = """import Lean
open Lean Elab Command

run_cmd do
  let f ← getFileName
  let dir := ((System.FilePath.mk f).parent.getD ".") / "build" / "Init"
  IO.FS.createDirAll dir
  IO.FS.writeFile (dir / "Prelude.olean") "not an olean"

theorem planted_ok : 2 + 2 = 4 := rfl
"""

GOOD = "theorem one_plus_one : 1 + 1 = 2 := rfl\n"
REFUSAL = ("leanchecker found a problem in Candidate\nuncaught exception: "
           "while replaying declaration 'smuggled':\n(kernel) declaration "
           "type mismatch, 'smuggled' has type\n  True\nbut it is expected "
           "to have type\n  False")


def _runner(*, checker=(0, ""), compile_rc=0, missing=False, calls=None,
            no_compiler=False):
    """Kernel and audit accept; the compile and leanchecker steps answer as
    told. Raising FileNotFoundError is how a missing binary shows up."""
    def run(argv, code):
        if calls is not None:
            calls.append(argv[0] if len(argv) == 1 else " ".join(argv))
        if argv[0] == "leanchecker":
            if missing:
                raise FileNotFoundError("leanchecker")
            return checker
        if "-o" in argv:
            if no_compiler:
                raise FileNotFoundError("lean")
            return compile_rc, "error: compile failed" if compile_rc else ""
        if "#print axioms" in code:
            return 0, "'one_plus_one' does not depend on any axioms"
        return 0, ""
    return run


def test_leanchecker_refusal_is_not_a_pass_and_names_the_reason():
    doc = lean_check(GOOD, runner=_runner(checker=(1, REFUSAL)))
    assert doc["passed"] is False
    assert "leanchecker replay refused" in doc["kernel_output"]
    assert "'smuggled'" in doc["kernel_output"]
    assert doc["validation_level"] == "print_axioms"
    assert doc["leanchecker"]["exit"] == 1
    r = LeanOracle(runner=_runner(checker=(1, REFUSAL))).verify(GOOD, None)
    assert r.verdict() == "FAIL"


def test_missing_leanchecker_is_unverifiable_never_pass():
    doc = lean_check(GOOD, runner=_runner(missing=True))
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "leanchecker-unavailable"
    assert "leanchecker could not be started" in doc["kernel_output"]
    assert doc["validation_level"] == "print_axioms"
    r = LeanOracle(runner=_runner(missing=True)).verify(GOOD, None)
    assert r.verdict() == "UNVERIFIABLE"
    assert r.unverifiable_reason == "TOOLCHAIN_MISSING"
    assert r.attribution.value == "ENVIRONMENT"


def test_compile_that_cannot_start_is_not_blamed_on_leanchecker():
    doc = lean_check(GOOD, runner=_runner(no_compiler=True))
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "lean-compile-unavailable"
    assert "lean could not be started to compile" in doc["kernel_output"]


def test_unloadable_import_is_unverifiable_not_a_refutation():
    unloaded = ("leanchecker found a problem in Candidate\nuncaught "
                "exception: unknown module prefix 'MyLib'\n\nNo directory "
                "'MyLib' or file 'MyLib.olean' in the search path entries:")
    doc = lean_check(GOOD, runner=_runner(checker=(1, unloaded)))
    assert doc["passed"] is None
    assert doc["unverifiable_reason"] == "leanchecker-import-unresolved"
    r = LeanOracle(runner=_runner(checker=(1, unloaded))).verify(GOOD, None)
    assert r.verdict() == "UNVERIFIABLE"


def test_a_declaration_name_cannot_pass_a_refusal_off_as_unloadable():
    # The fixed text is matched at the start of leanchecker's second line
    # only. A kernel refusal opens that line with "while replaying
    # declaration", so even a name carrying a newline lands on a later line.
    named = REFUSAL.replace(
        "'smuggled'", "'x\nuncaught exception: unknown module prefix 'y'")
    doc = lean_check(GOOD, runner=_runner(checker=(1, named)))
    assert doc["passed"] is False


def test_replay_success_passes_at_the_leanchecker_rung():
    doc = lean_check(GOOD, runner=_runner())
    assert doc["passed"] is True
    assert doc["validation_level"] == "leanchecker_replay"
    assert doc["validation_ladder"] == list(lean_replay.LADDER)
    rec = doc["leanchecker"]
    assert rec["mode"] == "plain" and rec["exit"] == 0
    assert rec["version"] == "injected"
    assert "no version flag" in rec["version_source"]
    r = LeanOracle(runner=_runner()).verify(GOOD, None)
    assert r.verdict() == "PASS"
    assert r.coverage["validation_level"] == "leanchecker_replay"
    assert any("plain mode" in line for line in r.does_not_prove)
    assert any("task is not read" in line for line in r.does_not_prove)


def test_a_failed_olean_compile_fails_closed():
    doc = lean_check(GOOD, runner=_runner(compile_rc=1))
    assert doc["passed"] is False
    assert ".olean" in doc["kernel_output"]


def test_replay_runs_only_after_the_kernel_and_the_audit_pass():
    calls = []

    def kernel_refuses(argv, code):
        calls.append(argv[0])
        return 1, "type mismatch"

    def audit_refuses(argv, code):
        calls.append(argv[0])
        if "#print axioms" in code:
            return 0, "'one_plus_one' depends on axioms: [Lean.ofReduceBool]"
        return 0, ""

    assert lean_check(GOOD, runner=kernel_refuses)["passed"] is False
    assert lean_check(GOOD, runner=audit_refuses)["passed"] is False
    assert calls and "leanchecker" not in calls


def test_a_file_with_no_named_theorem_stops_at_the_exit_code_rung():
    # Nothing was audited, so the level does not claim the axiom rung even
    # though the replay ran and accepted.
    doc = lean_check("example : True := trivial", runner=_runner())
    assert doc["passed"] is True
    assert doc["validation_level"] == "exit_code"
    assert doc["leanchecker"]["exit"] == 0


def test_toolchain_without_leanchecker_is_unverifiable(monkeypatch):
    import harness.lean_oracle as lo
    monkeypatch.setattr(lo, "_lean_exe", lambda: "lean")
    monkeypatch.setattr(lo, "_toolchain", lambda exe: "Lean (version 4.0.0)")
    monkeypatch.setattr(lo, "_run", _runner())
    monkeypatch.setattr(lean_replay, "toolchain_paths", lambda lean: (
        None, None, "leanchecker is not in this toolchain's bin directory"))
    doc = lean_check(GOOD)
    assert doc["passed"] is None
    assert "not in this toolchain" in doc["kernel_output"]


def test_level_is_cumulative():
    assert lean_replay.level(kernel_ok=False, audited=True,
                             replayed=True) == "none"
    assert lean_replay.level(kernel_ok=True, audited=False,
                             replayed=True) == "exit_code"
    assert lean_replay.level(kernel_ok=True, audited=True,
                             replayed=False) == "print_axioms"
    assert lean_replay.level(kernel_ok=True, audited=True,
                             replayed=True) == "leanchecker_replay"


def test_live_gate_needs_leanchecker_not_only_lean(monkeypatch):
    import harness.lean_oracle as lo
    monkeypatch.setattr(lo, "_lean_exe", lambda: "lean")
    monkeypatch.setattr(lean_replay, "toolchain_paths", lambda lean: (
        None, None, "leanchecker is not in this toolchain's bin directory"))
    assert leanchecker_available() is False


live = pytest.mark.skipif(not leanchecker_available(),
                          reason="lean or its leanchecker not installed")


@live
def test_live_smuggled_declaration_is_refused_by_the_replay():
    doc = lean_check(SMUGGLE)
    assert doc["passed"] is False, doc
    # The rungs below the replay pass this file; that is the defect.
    assert doc["axiom_footprint"] == {"bad": []}
    assert doc["validation_level"] == "print_axioms"
    assert "'smuggled'" in doc["kernel_output"]
    assert doc["leanchecker"]["exit"] != 0


@live
def test_live_control_passes_at_the_leanchecker_rung():
    doc = lean_check(CONTROL)
    assert doc["passed"] is True, doc["kernel_output"]
    assert doc["validation_level"] == "leanchecker_replay"
    assert doc["leanchecker"]["version"].startswith("Lean")


@live
def test_live_planted_init_in_the_build_dir_does_not_shadow_the_library():
    doc = lean_check(PLANT)
    assert doc["passed"] is True, doc["kernel_output"]
    assert doc["validation_level"] == "leanchecker_replay"


@live
def test_live_import_from_an_inherited_lean_path_passes(monkeypatch,
                                                         tmp_path):
    # `lake env` puts packages on LEAN_PATH. The kernel run and the compile
    # inherit it, so the replay must see the same entries (a sound proof
    # importing from one was FAIL before the replay kept them).
    lib = tmp_path / "lib"
    lib.mkdir()
    src = tmp_path / "MyLib.lean"
    src.write_text("def MyLibVal : Nat := 1\n", encoding="utf-8")
    rc, out = lean_replay.run_killable(
        [_lean_exe(), f"--root={tmp_path}", "-o", str(lib / "MyLib.olean"),
         str(src)], timeout=120, label="MyLib compile")
    assert rc == 0, out
    monkeypatch.setenv("LEAN_PATH", str(lib))
    doc = lean_check("import MyLib\ntheorem uses_lib : MyLibVal = 1 := rfl\n")
    assert doc["passed"] is True, doc["kernel_output"]
    assert doc["validation_level"] == "leanchecker_replay"
