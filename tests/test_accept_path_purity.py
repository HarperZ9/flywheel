"""A verdict is a pure function of (inputs, oracle version, config), full stop.

This one property subsumes every separate prohibition on ledger history,
selector scores, learned models, operator confidence, and incident counts
reaching a verdict. If none of those can influence the accept path, the accept
path cannot drift toward a preference economy.

The expert-grounding synthesis explicitly rejected static information-flow
analysis for this: it is undecidable in Python with dynamic imports and file IO.
So the test is a sandboxed replay instead. Destroy everything a prior run
produced, run again, and assert the verdict and every digest are unchanged. If
accumulated history reached the accept path, they would differ.
"""
import ast
import json
import shutil
import sys
from pathlib import Path

import pytest

from harness.gate import run_gate, rewitness_envelope


def test_the_verdict_does_not_depend_on_any_prior_record(tmp_path):
    first = run_gate(tmp_path / "run1")
    shutil.rmtree(tmp_path / "run1", ignore_errors=True)
    second = run_gate(tmp_path / "run2")

    assert second.verdict == first.verdict
    assert second.envelope_hash == first.envelope_hash
    assert second.claim_hash == first.claim_hash
    assert second.group_signal_hash == first.group_signal_hash


def test_a_prior_failing_record_cannot_condemn_a_later_candidate(tmp_path):
    """History must be unable to convict. A poisoned record in the output
    directory must not change what the oracle concludes."""
    clean = run_gate(tmp_path / "clean")

    poisoned = tmp_path / "poisoned"
    poisoned.mkdir(parents=True, exist_ok=True)
    (poisoned / "gate_envelope.json").write_text(
        json.dumps({"task_id": "gate-matmul-2x2x2", "candidate": "garbage",
                    "verdict": "FAIL", "oracle_output_hash": "deadbeef"}),
        encoding="utf-8")
    (poisoned / "gate_report.json").write_text(
        json.dumps({"verdict": "FAIL", "rewitness": "DRIFT"}), encoding="utf-8")

    after = run_gate(poisoned)
    assert after.verdict == clean.verdict
    assert after.envelope_hash == clean.envelope_hash
    assert after.claim_hash == clean.claim_hash


def test_a_prior_passing_record_cannot_absolve_a_bad_candidate(tmp_path):
    """The other direction, which is the one a reward hacker would want: a
    stored PASS must not make a broken candidate re-witness as MATCH."""
    run_gate(tmp_path)
    p = tmp_path / "gate_envelope.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["candidate"] = '{"n":2,"m":2,"p":2,"triples":[]}'   # verifiably wrong
    p.write_text(json.dumps(d, indent=2, sort_keys=True), encoding="utf-8")
    assert rewitness_envelope(p) == "DRIFT"


# Model-side harness modules: runtimes, the decision lane, and the classifier
# program. A verdict must not depend on any of them, directly or transitively.
FORBIDDEN_MODULES = {"serve", "proposer_local", "quant_dither",
                     "systemone_contract", "conformal"}
FORBIDDEN_PREFIXES = ("decision_", "classifier_")
IMPORT_CALLS = {"import_module", "__import__"}


def _verifier():
    scripts = str(Path(__file__).resolve().parent.parent / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import check_verifier_stdlib
    return check_verifier_stdlib


def _forbidden_harness(name: str) -> bool:
    return any(part in FORBIDDEN_MODULES or part.startswith(FORBIDDEN_PREFIXES)
               for part in name.split("."))


def _constant_import_call(node) -> str | None:
    """The module a constant-string importlib.import_module or __import__ names."""
    if not isinstance(node, ast.Call) or not node.args:
        return None
    func = getattr(node.func, "attr", getattr(node.func, "id", None))
    arg = node.args[0]
    if func in IMPORT_CALLS and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _model_side_imports(path: Path) -> list[str]:
    """train.* imports, static or by constant string, plus dynamic harness imports.

    The closure walker sees static harness imports only, and ignores the train
    package entirely. A dynamic import built from a non-constant string stays
    invisible to this check, as the walker's own docstring says.
    """
    hits = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and not node.level and node.module:
            hits.extend(n for n in [node.module] if n.split(".")[0] == "train")
        elif isinstance(node, ast.Import):
            hits.extend(a.name for a in node.names if a.name.split(".")[0] == "train")
        elif (name := _constant_import_call(node)) is not None:
            head, _, rest = name.partition(".")
            if head == "train" or head == "harness" and _forbidden_harness(rest):
                hits.append(name)
    return hits


def fence_violations(verifier) -> list[str]:
    """Every model-side module the verifier closure reaches, named."""
    reached, _ = verifier.closure(verifier.VERIFIER_ENTRY_POINTS)
    found = [f"harness.{name}" for name in sorted(reached) if _forbidden_harness(name)]
    for name in sorted(reached):
        path = verifier._module_path(name)
        if path is not None:
            found.extend(f"{name} imports {hit}" for hit in _model_side_imports(path))
    return found


def test_the_verifier_reaches_no_learned_model(tmp_path):
    """The C2 invariant, checked structurally over the import closure rather
    than by inspection: nothing the verifier path can reach imports a model
    runtime, the decision lane, the classifier program or the train package, so
    no learned model or fitted policy can sit on the accept path."""
    verifier = _verifier()
    reached, third_party_hits = verifier.closure(verifier.VERIFIER_ENTRY_POINTS)
    assert third_party_hits == []
    assert "gate" in reached and "evidence_json" in reached
    assert fence_violations(verifier) == []


def _copy_closure(verifier, root: Path) -> set[str]:
    """Copy exactly the files the real closure reaches into root/harness."""
    reached, _ = verifier.closure(verifier.VERIFIER_ENTRY_POINTS)
    for name in reached:
        source = verifier._module_path(name)
        if source is not None:
            target = root / "harness" / source.relative_to(verifier.HARNESS)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    return reached


@pytest.mark.parametrize("host, planted, stub, expected", [
    ("evidence_json", "from harness.decision_policy import fit_card", "decision_policy",
     "harness.decision_policy"),
    ("gate", "import harness.systemone_contract", "systemone_contract",
     "harness.systemone_contract"),
    ("evidence_json", "from .classifier_calibration import select_threshold",
     "classifier_calibration", "harness.classifier_calibration"),
    ("merkle", "from harness import conformal", "conformal", "harness.conformal"),
    ("merkle", "from train.classifier_token_runtime import TransformersTokenComparator",
     None, "merkle imports train.classifier_token_runtime"),
    ("merkle", "import importlib\nimportlib.import_module('harness.decision_policy')",
     None, "merkle imports harness.decision_policy"),
])
def test_the_fence_fires_on_a_planted_model_side_import(
        tmp_path, monkeypatch, host, planted, stub, expected):
    """A fence that never fires proves nothing. Copy the real closure, confirm
    the copy is clean and walks identically, then plant one import in a reached
    module and require the fence to name it."""
    verifier = _verifier()
    real = _copy_closure(verifier, tmp_path)
    monkeypatch.setattr(verifier, "HARNESS", tmp_path / "harness")
    assert verifier.closure(verifier.VERIFIER_ENTRY_POINTS)[0] == real
    assert fence_violations(verifier) == []

    target = tmp_path / "harness" / f"{host}.py"
    target.write_text(target.read_text(encoding="utf-8") + "\n" + planted + "\n",
                      encoding="utf-8")
    if stub:
        (tmp_path / "harness" / f"{stub}.py").write_text(
            "def fit_card():\n    return None\n", encoding="utf-8")
    assert expected in fence_violations(verifier)
