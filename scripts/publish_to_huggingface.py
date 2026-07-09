"""Guarded Hugging Face publisher for the Flywheel local models.

This is the one place the operator's publication rule lives as code, not prose:

  Do not publish until the benchmark that shows efficiency is measurable to an
  outside observer, and never publish a false capability claim.

So this command refuses to upload unless ALL of these hold:
  1. A Hugging Face token is available (env HF_TOKEN, or the huggingface_hub
     stored login). We never take a token on the command line.
  2. The release-readiness receipt for the model is READY_TO_STAGE / static
     release-ready, and the HF stage receipt is not DO_NOT_UPLOAD.
  3. The benchmark gate is satisfied. Either the confidence-interval receipt
     shows the verified-vs-single-shot difference EXCLUDES zero (a real,
     outside-observer-measurable effect), OR the operator passes
     --acknowledge-null-result to publish the honest null on purpose. Publishing
     a FALSE uplift is never allowed; publishing a truthful "no uplift, but
     reproducible receipts and local cost" is allowed once acknowledged.
  4. --confirm-upload is passed. Without it this is a dry run that only prints
     what it would do.

Nothing here trains, quantizes, or fabricates evidence. It reads receipts and,
only when every gate is green, shells out to the Hugging Face CLI. The upload
itself stays an explicit operator action.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


READY_VERDICTS = {"MODEL_RELEASE_READY_STATIC"}
READY_PUBLISH_STATUS = {"READY_TO_STAGE"}
BLOCKED_UPLOAD_STATUS = {"DO_NOT_UPLOAD"}


def _load(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, f"missing:{path}"
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}:{path}"


def _token_present() -> bool:
    if os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"):
        return True
    try:
        from huggingface_hub import HfApi  # noqa: PLC0415
        HfApi().whoami()
        return True
    except Exception:
        return False


def _readiness_row(readiness: dict[str, Any], model: str) -> dict[str, Any] | None:
    for row in readiness.get("models", []):
        if str(row.get("model", "")).upper() == model.upper():
            return row
    return None


def _stage_row(stage: dict[str, Any], model: str) -> dict[str, Any] | None:
    for row in stage.get("models", []):
        if str(row.get("model", "")).upper() == model.upper():
            return row
    return None


def _benchmark_gate(ci: dict[str, Any] | None, *, acknowledge_null: bool) -> dict[str, Any]:
    """Green if any scorecard difference excludes zero, or the operator
    acknowledges publishing the honest null."""
    if not ci:
        return {"passed": False, "reason": "no confidence-interval receipt found",
                "excludes_zero": False}
    excludes_zero = False
    detail = []
    for name, result in ci.items():
        d = result.get("difference") or {}
        inc = bool(d.get("includes_zero", True))
        detail.append({"scorecard": name, "point": d.get("point"),
                       "ci_95": d.get("ci_95"), "includes_zero": inc,
                       "method": d.get("method")})
        if d and not inc:
            excludes_zero = True
    if excludes_zero:
        return {"passed": True, "reason": "a scorecard difference excludes zero "
                "(outside-observer-measurable effect)", "excludes_zero": True,
                "detail": detail}
    if acknowledge_null:
        return {"passed": True, "reason": "operator acknowledged publishing the "
                "honest null result (no uplift claimed; receipts + local cost are "
                "the claims)", "excludes_zero": False, "detail": detail}
    return {"passed": False, "reason": "no scorecard difference excludes zero yet; "
            "the outside-observer instrument (100-task lane) is not conclusive. "
            "Re-run when it is, or pass --acknowledge-null-result to publish the "
            "honest null on purpose.", "excludes_zero": False, "detail": detail}


def evaluate_gates(*, model: str, readiness: dict[str, Any] | None,
                   stage: dict[str, Any] | None, ci: dict[str, Any] | None,
                   token_present: bool, operator_approved: bool,
                   acknowledge_null: bool) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []

    gates.append({"gate": "hf_token_present", "passed": token_present,
                  "detail": "HF_TOKEN / stored login" if token_present
                  else "no Hugging Face token; export HF_TOKEN or run huggingface-cli login"})

    r_row = _readiness_row(readiness or {}, model)
    trained = bool(r_row and r_row.get("trained_artifact_present"))
    ready = bool(r_row and (r_row.get("verdict") in READY_VERDICTS
                            or r_row.get("enterprise_release_ready")))
    gates.append({"gate": "trained_artifact_present", "passed": trained,
                  "detail": "" if trained else "no trained artifact for this track; refuse"})
    gates.append({"gate": "release_ready_static", "passed": ready,
                  "detail": (r_row or {}).get("verdict", "no readiness row")})

    s_row = _stage_row(stage or {}, model)
    stage_ok = bool(s_row and s_row.get("upload_status") not in BLOCKED_UPLOAD_STATUS)
    gates.append({"gate": "stage_not_blocked", "passed": stage_ok,
                  "detail": (s_row or {}).get("upload_status", "no stage row")})

    gates.append({"gate": "operator_upload_approved", "passed": operator_approved,
                  "detail": "operator --approve-upload"
                  if operator_approved else "operator upload approval not given"})

    bench = _benchmark_gate(ci, acknowledge_null=acknowledge_null)
    gates.append({"gate": "benchmark_outside_observer", "passed": bench["passed"],
                  "detail": bench["reason"]})

    all_green = all(g["passed"] for g in gates)
    repo_id = (s_row or {}).get("repo_id", f"HarperZ9/flywheel-local-coder-{model.lower()}")
    model_root = (r_row or {}).get("root", "")
    return {
        "model": model, "repo_id": repo_id, "model_root": model_root,
        "gates": gates, "all_green": all_green,
        "benchmark_detail": bench.get("detail", []),
        "decision": "READY_TO_UPLOAD" if all_green else "BLOCKED",
    }


def _upload(repo_id: str, model_root: str, *, private: bool) -> int:
    hf = shutil.which("hf") or shutil.which("huggingface-cli")
    if not hf:
        print("ERROR: neither `hf` nor `huggingface-cli` is on PATH; cannot upload.")
        return 3
    cmd = [hf, "upload", repo_id, model_root, "--repo-type", "model"]
    if private:
        cmd.append("--private")
    print("RUNNING:", " ".join(cmd))
    return subprocess.run(cmd).returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="14B", help="model track to publish (default 14B)")
    ap.add_argument("--dist", default="artifacts/exe", help="dir holding the *.local.json receipts")
    ap.add_argument("--ci-artifact", default="artifacts/flywheel-local-coder-14b-benchmark-ci.json")
    ap.add_argument("--approve-upload", action="store_true",
                    help="operator approval for this upload (per-run, not stored)")
    ap.add_argument("--acknowledge-null-result", action="store_true",
                    help="publish the honest null (no uplift) on purpose")
    ap.add_argument("--confirm-upload", action="store_true",
                    help="actually upload; without it this is a dry run")
    ap.add_argument("--private", action="store_true")
    args = ap.parse_args(argv)

    dist = Path(args.dist)
    readiness, _ = _load(dist / "model_release_readiness.local.json")
    stage, _ = _load(dist / "huggingface_release_stage.local.json")
    ci, _ = _load(Path(args.ci_artifact))

    report = evaluate_gates(
        model=args.model, readiness=readiness, stage=stage, ci=ci,
        token_present=_token_present(), operator_approved=args.approve_upload,
        acknowledge_null=args.acknowledge_null_result,
    )
    print(json.dumps(report, indent=2))

    if not report["all_green"]:
        blocked = [g["gate"] for g in report["gates"] if not g["passed"]]
        print(f"\nBLOCKED. Unmet gates: {', '.join(blocked)}. Nothing was uploaded.")
        return 1
    if not args.confirm_upload:
        print(f"\nAll gates green for {report['repo_id']}. DRY RUN. "
              "Re-run with --confirm-upload to upload.")
        return 0
    print(f"\nAll gates green. Uploading {report['repo_id']} from {report['model_root']} ...")
    return _upload(report["repo_id"], report["model_root"], private=args.private)


if __name__ == "__main__":
    raise SystemExit(main())
