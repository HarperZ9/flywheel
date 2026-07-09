"""Emit a non-executing embodied realtime multimodal benchmark plan."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.provider_roles import provider_roles_for  # noqa: E402


SCHEMA = "harness.embodied-realtime-multimodal/v1"
DEFAULT_CONTRACT = "C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json"
DEFAULT_ARTIFACT_DIR = "C:/tmp/embodied_realtime_multimodal"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_int_csv(value: str) -> list[int]:
    parsed = []
    for item in split_csv(value):
        parsed.append(int(item))
    return parsed or [250, 500, 1000]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prompt_hash(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def _coverage_unit(probe_id: str) -> str:
    mapping = {
        "tiny_robotics_latency": "tiny_model_robotics_latency",
        "code_drawn_visual_reasoning": "code_drawn_letter_grid_spatial_fix",
        "simplified_sensor_projection": "synthetic_vision_token_grounding",
        "affective_drift_probe": "affective_jealousy_possessiveness_probe",
    }
    return mapping.get(probe_id, probe_id)


def build_plan(
    contract: dict[str, Any],
    *,
    contract_path: str,
    contract_sha256: str,
    provider_roles: list[str],
    latency_budgets_ms: list[int],
    artifact_dir: str,
    run_id: str = "",
) -> dict[str, Any]:
    probes = contract.get("probe_groups") if isinstance(contract.get("probe_groups"), list) else []
    benchmark_id = str(contract.get("benchmark_id", "embodied_realtime_multimodal_pressure"))
    dataset_lanes = [
        str(item)
        for item in (contract.get("dataset_lanes") if isinstance(contract.get("dataset_lanes"), list) else [])
        if item
    ]
    pressure_variables = [
        str(item)
        for item in (contract.get("pressure_variables") if isinstance(contract.get("pressure_variables"), list) else [])
        if item
    ]
    rows: list[dict[str, Any]] = []
    dry_rows: list[dict[str, Any]] = []
    for probe in probes:
        if not isinstance(probe, dict):
            continue
        probe_id = str(probe.get("id", ""))
        question = str(probe.get("question", ""))
        measurements = [str(item) for item in probe.get("measurements", []) if item] if isinstance(probe.get("measurements"), list) else []
        coverage_unit = _coverage_unit(probe_id)
        for provider_role in provider_roles:
            for latency_budget_ms in latency_budgets_ms:
                unit_id = f"{coverage_unit}:{provider_role}:{latency_budget_ms}ms"
                expected_json = str(Path(artifact_dir) / f"{probe_id}_{provider_role}_{latency_budget_ms}ms.json")
                expected_md = str(Path(artifact_dir) / f"{probe_id}_{provider_role}_{latency_budget_ms}ms.md")
                row = {
                    "schema": "harness.embodied-realtime-probe/v1",
                    "benchmark_id": benchmark_id,
                    "probe_id": probe_id,
                    "coverage_unit": unit_id,
                    "base_coverage_unit": coverage_unit,
                    "dataset_lanes": dataset_lanes,
                    "pressure_variables": pressure_variables,
                    "provider_role": provider_role,
                    "latency_budget_ms": latency_budget_ms,
                    "question_hash": prompt_hash(probe_id, question),
                    "prompt_hash": prompt_hash(probe_id, question, provider_role, latency_budget_ms),
                    "measurements": measurements,
                    "expected_artifacts": [expected_json, expected_md],
                    "status": "planned",
                    "execution_required_for_score": True,
                }
                rows.append(row)
                dry_rows.append({
                    "schema": "harness.embodied-realtime-scorecard-row/v1",
                    "benchmark_id": benchmark_id,
                    "probe_id": probe_id,
                    "coverage_unit": unit_id,
                    "base_coverage_unit": coverage_unit,
                    "provider_role": provider_role,
                    "latency_budget_ms": latency_budget_ms,
                    "dataset_lane": dataset_lanes[0] if dataset_lanes else "",
                    "pressure_variables": pressure_variables,
                    "status": "planned",
                    "failure_class": "not_executed",
                    "quality_score": None,
                    "latency_ms": None,
                    "receipt_hash": "",
                    "execution_required_for_score": True,
                })
    return {
        "schema": SCHEMA,
        "timestamp_utc": utc_now(),
        "run_id": run_id,
        "contract_path": contract_path,
        "contract_sha256": contract_sha256,
        "benchmark_id": benchmark_id,
        "provider_roles": provider_roles,
        "latency_budgets_ms": latency_budgets_ms,
        "dataset_lanes": dataset_lanes,
        "pressure_variables": pressure_variables,
        "model_leads_unverified": contract.get("source_feedback", {}).get("model_leads_unverified", [])
        if isinstance(contract.get("source_feedback"), dict)
        else [],
        "probe_rows": rows,
        "dry_scorecard_rows": dry_rows,
        "summary": {
            "probes": len(probes),
            "providers": len(provider_roles),
            "latency_budgets": len(latency_budgets_ms),
            "planned_probe_rows": len(rows),
            "planned_scorecard_rows": len(dry_rows),
            "execution_status": "not_executed",
        },
        "limitations": [
            "This artifact is metadata-only and does not call models, endpoints, sensors, or renderers.",
            "Named model leads are unverified until model cards or local manifests are inspected.",
            "Dry scorecard rows must not be counted as executed benchmark evidence.",
        ],
    }


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Embodied realtime multimodal benchmark plan",
        "",
        f"- Schema: `{plan['schema']}`",
        f"- Timestamp UTC: `{plan['timestamp_utc']}`",
        f"- Benchmark id: `{plan['benchmark_id']}`",
        f"- Contract: `{plan['contract_path']}`",
        f"- Contract sha256: `{plan['contract_sha256']}`",
        f"- Provider roles: `{', '.join(plan['provider_roles'])}`",
        f"- Latency budgets ms: `{', '.join(str(item) for item in plan['latency_budgets_ms'])}`",
        f"- Dataset lanes: `{', '.join(plan['dataset_lanes'])}`",
        f"- Pressure variables: `{', '.join(plan['pressure_variables'])}`",
        f"- Planned probe rows: `{plan['summary']['planned_probe_rows']}`",
        f"- Planned scorecard rows: `{plan['summary']['planned_scorecard_rows']}`",
        "",
        "## Probe rows",
        "",
        "| Probe | Provider | Budget ms | Coverage unit | Measurements |",
        "|---|---|---:|---|---|",
    ]
    for row in plan["probe_rows"]:
        lines.append(
            "| {probe} | {provider} | {budget} | {unit} | {measurements} |".format(
                probe=row.get("probe_id", ""),
                provider=row.get("provider_role", ""),
                budget=row.get("latency_budget_ms", ""),
                unit=row.get("coverage_unit", ""),
                measurements=", ".join(row.get("measurements", [])),
            )
        )
    lines.extend(["", "## Limitations", ""])
    for item in plan["limitations"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def store_plan(
    plan: dict[str, Any],
    *,
    store_root: str,
    run_id: str,
    artifacts: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="embodied_realtime_multimodal_plan",
            body=plan,
            run_id=run_id,
            verdict="EMBODIED_REALTIME_PLAN_RECORDED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--providers", default="dry")
    parser.add_argument("--latency-budgets-ms", default="250,500,1000")
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--out", default="C:/tmp/embodied_realtime_multimodal_plan.json")
    parser.add_argument("--markdown-out", default="C:/tmp/embodied_realtime_multimodal_plan.md")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    contract_path = Path(args.contract)
    contract = load_json(contract_path)
    plan = build_plan(
        contract,
        contract_path=str(contract_path),
        contract_sha256=file_sha256(contract_path),
        provider_roles=provider_roles_for(split_csv(args.providers)) or ["dry_fixture"],
        latency_budgets_ms=parse_int_csv(args.latency_budgets_ms),
        artifact_dir=args.artifact_dir,
        run_id=args.run_id,
    )
    json_text = json.dumps(plan, indent=2, sort_keys=True)
    md_text = render_markdown(plan)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_plan(
        plan,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "embodied-realtime-multimodal-json"),
            (md_path, "embodied-realtime-multimodal-markdown"),
        ],
    )
    if store_outputs:
        plan = {**plan, "store_outputs": store_outputs}
        json_text = json.dumps(plan, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
