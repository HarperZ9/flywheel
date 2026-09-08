"""Reviewed entrypoint for the local finalizer held-out candidate-prefix experiment."""
from __future__ import annotations
import argparse, json
from datetime import UTC, datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.cross_harness_cli import _load, _recheck_local_gate, build_adapter_registry
from harness.cross_harness_manifest import _prompt_text, sha256_text
from harness.local_finalizer_experiment import (FIXED_PARAMS, LocalCandidatePrefixRunner,
    build_nonleaky_overlay, run_candidate_prefix_experiment)

EXPERIMENT_TASK_SET_ID = "local_finalizer_heldout_revised_20260908"


def _task_map(task_set):
    return {row["id"]: row for row in task_set.get("tasks", []) if isinstance(row, dict) and row.get("id")}


def _sha(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _derived_prompt(task_set: dict, contract: dict, base: dict, task_id: str, inputs: list[str]) -> tuple[str, str]:
    prompt = _prompt_text({**task_set, "task_set_id": EXPERIMENT_TASK_SET_ID},
                          contract, {**base, "id": task_id, "required_inputs": inputs})
    return prompt, sha256_text(prompt)


def build_tasks(source_root: Path, task_set_path: Path, contract_path: Path, run_root: Path):
    task_set, contract = _load(task_set_path), _load(contract_path)
    overlay_root = run_root / "task-overlay"
    overlay = {row["base_task_id"]: row for row in build_nonleaky_overlay(source_root, overlay_root)}
    by_id = _task_map(task_set); out = []
    for base_id in ["agt-015-evidence-bound-reporting", "agt-016-source-contradiction-detection"]:
        base, row = by_id[base_id], overlay[base_id]
        prompt, prompt_hash = _derived_prompt(task_set, contract, base, row["task_id"], [row["visible_fixture"]])
        out.append({"task_set_id": EXPERIMENT_TASK_SET_ID, "task_id": row["task_id"],
            "prompt": prompt, "raw_prompt_sha256": prompt_hash,
            "expected_artifacts": base["expected_artifacts"],
            "visible_sources": {row["visible_fixture"]: overlay_root / row["visible_fixture"]},
            "visible_input_sha256s": row["visible_input_sha256s"],
            "oracle_input_sha256s": row["oracle_input_sha256s"], "oracle_root": overlay_root,
            "oracle": {**base["oracle"], "fixture": row["oracle_fixture"],
                       "expected_artifacts": base["expected_artifacts"]}})
    base = by_id["agt-017-budgeted-evidence-selection"]
    rel = base["required_inputs"][0]; path = source_root / rel
    prompt, prompt_hash = _derived_prompt(task_set, contract, base, base["id"], [rel])
    out.append({"task_set_id": EXPERIMENT_TASK_SET_ID, "task_id": base["id"],
        "prompt": prompt, "raw_prompt_sha256": prompt_hash,
        "expected_artifacts": base["expected_artifacts"], "visible_sources": {rel: path},
        "visible_input_sha256s": {rel: _sha(path)}, "oracle_input_sha256s": {rel: _sha(path)},
        "oracle_root": source_root, "oracle": {**base["oracle"], "expected_artifacts": base["expected_artifacts"]}})
    return out


def parser():
    p = argparse.ArgumentParser(description="Run the reviewed local finalizer C/A/B candidate-prefix experiment.")
    for name in ("source-root", "task-set", "contract", "runtime-matrix", "endpoint-gate", "gate-run-id", "private-run-root"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--provider-role", default="local_14b")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    run_root = Path(args.private_run_root)
    if run_root.exists():
        raise ValueError("private run root already exists")
    run_root.mkdir(parents=True)
    matrix = _load(Path(args.runtime_matrix))
    _recheck_local_gate(matrix, Path(args.endpoint_gate), args.gate_run_id,
                        [args.provider_role], datetime.now(UTC), 900)
    adapters = build_adapter_registry(matrix, [args.provider_role])
    tasks = build_tasks(Path(args.source_root), Path(args.task_set), Path(args.contract), run_root)
    params = {**FIXED_PARAMS, "provider_role": args.provider_role}
    runner = LocalCandidatePrefixRunner(adapters[args.provider_role], Path(args.source_root), params)
    summary = run_candidate_prefix_experiment(tasks, run_root / "primary", params,
        candidate_runner=runner.candidate, finalizer_runner=runner.finalizer)
    print(json.dumps({"run_summary": str(run_root / "primary" / "run-summary.json"),
                      "rows": len(summary["rows"]), "params_sha256": summary["params_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


