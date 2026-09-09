"""Gather product workflows for the product E2E runner."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from harness.e2e_adapters import CliProcessJourneyAdapter, JourneyStepResult, MCPStdioJourneyAdapter
from harness.e2e_journey_manifest import JourneyManifest


def _selection_bounds(source_text: str, oracle: dict[str, Any]) -> tuple[int, int, str]:
    start = source_text.index(str(oracle["start_marker"]))
    end = source_text.index(str(oracle["end_marker"]), start + len(str(oracle["start_marker"])))
    selected = source_text[start:end].rstrip()
    return start, max(1, len(selected)), selected


def _require_completed(step: JourneyStepResult) -> dict[str, Any]:
    row = step.to_dict()
    if step.status != "completed" or step.parsed_json is None:
        raise RuntimeError(json.dumps(row, sort_keys=True))
    return step.parsed_json


def _tamper(corpus: Path) -> None:
    objects = sorted((corpus / "objects").glob("*/*"))
    if not objects:
        raise RuntimeError("corpus_object_not_found")
    objects[0].write_text("tampered E2E corpus body with different bytes\n", encoding="utf-8")


def _tamper_status(step: JourneyStepResult) -> dict[str, Any]:
    text = (step.stderr_tail + "\n" + step.stdout).casefold()
    return {
        "status": "pass" if step.status == "failed" and ("corrupt" in text or "body status" in text) else "fail",
        "step_status": step.status,
        "evidence": (step.stderr_tail or step.stdout)[-1000:],
    }


def _run_cli_flow(manifest: JourneyManifest, runtime: dict[str, Any], workspace: Path,
                  owner_state: Path, source_text_path: Path, corpus: Path,
                  select_start: int, select_limit: int) -> dict[str, Any]:
    adapter = CliProcessJourneyAdapter(Path(runtime["executable"]), timeout_seconds=30)
    steps: list[JourneyStepResult] = []
    try:
        acquire = adapter.run_json(["docs", str(source_text_path), "--store", str(corpus), "--json"],
                                   cwd=owner_state, step_id="acquire")
        steps.append(acquire); _require_completed(acquire)
        inspect = adapter.run_json(["corpus", "context", str(corpus), "--json"],
                                   cwd=owner_state, step_id="inspect")
        steps.append(inspect); inspected = _require_completed(inspect)
        row_ref = inspected["rows"][0]["row_ref"]
        digest = inspected["corpus_digest"]
        selected_ref = f"{row_ref}:{select_start}:{select_limit}"
        select = adapter.run_json(["corpus", "context", str(corpus), "--select", selected_ref,
                                   "--expect-digest", digest, "--json"], cwd=owner_state, step_id="select")
        steps.append(select); selected = _require_completed(select)
        wrong = adapter.run_json(["corpus", "context", str(corpus), "--select", row_ref,
                                  "--expect-digest", digest, "--json"], cwd=owner_state,
                                 step_id="wrong_body_control")
        steps.append(wrong); wrong_payload = _require_completed(wrong)
        _tamper(corpus)
        tamper = adapter.run_json(["corpus", "context", str(corpus), "--select", row_ref,
                                   "--expect-digest", digest, "--json"], cwd=owner_state,
                                  step_id="tamper_refusal_control")
        steps.append(tamper)
        return {"steps": [step.to_dict() for step in steps], "selected_payload": selected,
                "wrong_body_payload": wrong_payload, "tamper_refusal": _tamper_status(tamper)}
    finally:
        adapter.close()


def _run_mcp_flow(manifest: JourneyManifest, runtime: dict[str, Any], workspace: Path,
                  owner_state: Path, source_text_path: Path, corpus: Path,
                  select_start: int, select_limit: int) -> dict[str, Any]:
    adapter = MCPStdioJourneyAdapter(Path(runtime["executable"]), cwd=owner_state, timeout_seconds=30)
    steps: list[JourneyStepResult] = []
    try:
        adapter.start()
        config = {"jobs": [{"source": "docs", "target": str(source_text_path)}],
                  "scope": [], "store": str(corpus)}
        acquire = adapter.call_json("gather.run", {"config": config}, step_id="acquire")
        steps.append(acquire); _require_completed(acquire)
        inspect = adapter.call_json("gather.context", {"corpus": str(corpus)}, step_id="inspect")
        steps.append(inspect); inspected = _require_completed(inspect)
        row_ref = inspected["rows"][0]["row_ref"]
        digest = inspected["corpus_digest"]
        selected_ref = f"{row_ref}:{select_start}:{select_limit}"
        select = adapter.call_json("gather.context", {"corpus": str(corpus), "select": [selected_ref],
                                  "expected_corpus_digest": digest}, step_id="select")
        steps.append(select); selected = _require_completed(select)
        wrong = adapter.call_json("gather.context", {"corpus": str(corpus), "select": [row_ref],
                                 "expected_corpus_digest": digest}, step_id="wrong_body_control")
        steps.append(wrong); wrong_payload = _require_completed(wrong)
        _tamper(corpus)
        tamper = adapter.call_json("gather.context", {"corpus": str(corpus), "select": [row_ref],
                                  "expected_corpus_digest": digest}, step_id="tamper_refusal_control")
        steps.append(tamper)
        return {"steps": [step.to_dict() for step in steps], "selected_payload": selected,
                "wrong_body_payload": wrong_payload, "tamper_refusal": _tamper_status(tamper)}
    finally:
        adapter.close()


def run_gather_context_flow(manifest: JourneyManifest, runtime: dict[str, Any],
                            workspace: Path, owner_state: Path) -> dict[str, Any]:
    source_text_path = workspace / manifest.fixture_relative("source_text")
    corpus = owner_state / "corpus"
    source_text = source_text_path.read_text(encoding="utf-8")
    start, limit, expected_text = _selection_bounds(source_text, manifest.oracle)
    if manifest.runtime.kind == "cli_process":
        result = _run_cli_flow(manifest, runtime, workspace, owner_state, source_text_path, corpus, start, limit)
    elif manifest.runtime.kind == "mcp_stdio":
        result = _run_mcp_flow(manifest, runtime, workspace, owner_state, source_text_path, corpus, start, limit)
    else:
        raise RuntimeError(f"unsupported runtime: {manifest.runtime.kind}")
    result["expected_selection"] = {
        "text": expected_text,
        "sha256": hashlib.sha256(expected_text.encode("utf-8")).hexdigest(),
        "start": start,
        "limit": limit,
    }
    return result
