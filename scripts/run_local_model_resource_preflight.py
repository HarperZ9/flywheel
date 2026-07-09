"""Emit GPU resource preflight for local model serve launches."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.benchmark_receipts import store_benchmark_outputs  # noqa: E402
from harness.membudget import QWEN_14B, QWEN_32B, estimate_vram, recommend  # noqa: E402


GpuProbe = Callable[[], list[dict[str, Any]]]

MODEL_PROFILES = {
    "14b": {
        "profile": QWEN_14B,
        "lora_trainable": 70_000_000,
        "seq_len": 2048,
    },
    "32b": {
        "profile": QWEN_32B,
        "lora_trainable": 134_000_000,
        "seq_len": 2048,
    },
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _load_profiles(path_text: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if data.get("schema") == "harness.model-endpoint-profile/v1":
        return [data]
    rows = data.get("profiles") if isinstance(data.get("profiles"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _nvidia_smi_probe() -> list[dict[str, Any]]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    rows = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5:
            continue
        rows.append({
            "name": parts[0],
            "memory_total_gb": round(float(parts[1]) / 1024, 3),
            "memory_used_gb": round(float(parts[2]) / 1024, 3),
            "memory_free_gb": round(float(parts[3]) / 1024, 3),
            "utilization_gpu_pct": float(parts[4]),
        })
    return rows


def _select_profiles(profiles: list[dict[str, Any]], *, models: list[str]) -> list[dict[str, Any]]:
    wanted = {item.lower() for item in models}
    return [
        profile
        for profile in profiles
        if str(profile.get("backend", "")).lower() == "serve"
        and (not wanted or str(profile.get("model", "")).lower() in wanted)
    ]


def _model_key(profile: dict[str, Any]) -> str:
    value = str(profile.get("model_key", "")).lower()
    if value:
        return value
    return str(profile.get("model", "")).lower().replace(" ", "")


def _row_for_profile(profile: dict[str, Any], gpu: dict[str, Any] | None) -> dict[str, Any]:
    key = _model_key(profile)
    spec = MODEL_PROFILES.get(key)
    free_gb = float((gpu or {}).get("memory_free_gb", 0.0))
    total_gb = float((gpu or {}).get("memory_total_gb", 0.0))
    row = {
        "schema": "harness.local-model-resource-preflight.row/v1",
        "profile_id": profile.get("profile_id", ""),
        "model": profile.get("model", ""),
        "model_key": key,
        "endpoint_url": profile.get("endpoint_url", ""),
        "expected_model_ref": profile.get("model_ref", ""),
        "model_root": profile.get("model_root", ""),
        "root_exists": bool(profile.get("root_exists")),
        "gpu_name": (gpu or {}).get("name", ""),
        "gpu_total_gb": total_gb,
        "gpu_free_gb": free_gb,
        "gpu_used_gb": float((gpu or {}).get("memory_used_gb", 0.0)),
        "estimated_required_gb": 0.0,
        "estimated_full_card_fits": False,
        "current_free_fits": False,
        "verdict": "unsupported_model",
        "recommendation": "",
    }
    if gpu is None:
        row["verdict"] = "gpu_unobserved"
        row["recommendation"] = "record GPU telemetry before starting a local serve process"
        return row
    if not row["root_exists"]:
        row["verdict"] = "model_root_missing"
        row["recommendation"] = "repair endpoint profile root before launch"
        return row
    if spec is None:
        row["recommendation"] = "add a memory profile before launch"
        return row

    estimate = estimate_vram(
        spec["profile"],
        seq_len=spec["seq_len"],
        lora_trainable=spec["lora_trainable"],
        target_gb=total_gb or 24.0,
    )
    fit_rec = recommend(
        spec["profile"],
        target_gb=total_gb or 24.0,
        want_seq_len=spec["seq_len"],
        lora_trainable=spec["lora_trainable"],
    )
    row["estimated_required_gb"] = round(estimate.total_gb, 3)
    row["estimated_full_card_fits"] = bool(estimate.fits)
    row["current_free_fits"] = free_gb >= estimate.total_gb + 0.5
    if row["current_free_fits"]:
        row["verdict"] = "launch_resource_ready"
        row["recommendation"] = "start is resource-permitted by current free VRAM estimate"
    elif row["estimated_full_card_fits"]:
        row["verdict"] = "blocked_by_current_gpu_pressure"
        row["recommendation"] = "free GPU memory or stop another local model before launching"
    else:
        row["verdict"] = "requires_offload_or_smaller_runtime"
        row["recommendation"] = fit_rec.offload_strategy
    return row


def build_report(
    *,
    profile_artifact: str,
    models: list[str],
    gpu_probe: GpuProbe = _nvidia_smi_probe,
) -> dict[str, Any]:
    profiles = _load_profiles(profile_artifact)
    selected = _select_profiles(profiles, models=models)
    gpus = gpu_probe()
    primary_gpu = gpus[0] if gpus else None
    rows = [_row_for_profile(profile, primary_gpu) for profile in selected]
    blocking = {
        "gpu_unobserved",
        "model_root_missing",
        "unsupported_model",
        "blocked_by_current_gpu_pressure",
        "requires_offload_or_smaller_runtime",
    }
    return {
        "schema": "harness.local-model-resource-preflight/v1",
        "timestamp_utc": now_utc(),
        "profile_artifact": profile_artifact,
        "gpu_observed": bool(gpus),
        "gpus": gpus,
        "rows": rows,
        "summary": {
            "profiles_loaded": len(profiles),
            "profiles_selected": len(selected),
            "ready_rows": sum(1 for row in rows if row["verdict"] == "launch_resource_ready"),
            "blocking_rows": sum(1 for row in rows if row["verdict"] in blocking),
            "models_observed": sorted({str(row.get("model", "")) for row in rows if row.get("model")}),
            "verdicts": sorted({str(row.get("verdict", "")) for row in rows if row.get("verdict")}),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Local model resource preflight",
        "",
        f"- Schema: `{report['schema']}`",
        f"- GPU observed: `{str(report['gpu_observed']).lower()}`",
        f"- Profiles selected: `{summary['profiles_selected']}` / `{summary['profiles_loaded']}`",
        f"- Ready rows: `{summary['ready_rows']}`",
        f"- Blocking rows: `{summary['blocking_rows']}`",
        "",
        "| Model | Endpoint | GPU free GB | Est. required GB | Verdict | Recommendation |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            "| {model} | {endpoint} | {free} | {required} | {verdict} | {rec} |".format(
                model=row.get("model", ""),
                endpoint=row.get("endpoint_url", ""),
                free=row.get("gpu_free_gb", 0.0),
                required=row.get("estimated_required_gb", 0.0),
                verdict=row.get("verdict", ""),
                rec=row.get("recommendation", ""),
            )
        )
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-artifact", required=True)
    parser.add_argument("--models", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--strict-exit", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        profile_artifact=args.profile_artifact,
        models=split_csv(args.models),
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = store_benchmark_outputs(
        report,
        store_root=args.store_root,
        kind="local_model_resource_preflight",
        run_id=args.run_id,
        verdict="LOCAL_MODEL_RESOURCE_READY" if report["summary"]["blocking_rows"] == 0 else "LOCAL_MODEL_RESOURCE_BLOCKED",
        artifact_paths=[
            (json_path, "local-model-resource-preflight-json"),
            (md_path, "local-model-resource-preflight-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 1 if args.strict_exit and report["summary"]["blocking_rows"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
