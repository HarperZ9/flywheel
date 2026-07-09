"""Emit metadata-only Forum route receipts for closed-loop harness runs.

The command does not call the Forum MCP server. It records route request text,
prompt hashes, and optional observed Forum route-frame fields when an agent has
already called `forum.route` and wants that evidence preserved in the harness
store without embedding the whole live tool payload in model context.
"""

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


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def text_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    if normalized in {"", "unknown", "none", "null"}:
        return None
    raise argparse.ArgumentTypeError(f"expected bool-ish value, got {value!r}")


def route_row(
    *,
    route_id: str,
    text: str,
    observed_decided: str,
    observed_confidence: float | None,
    observed_needs_escalation: bool | None,
    observed_domain: str,
    observed_intent: str,
    observed_posture: str,
    observed_proof_lane: str,
    observed_domain_lane: str,
    observed_human_contract: str,
    observed_source: str,
) -> dict[str, Any]:
    observed = any([
        observed_decided,
        observed_confidence is not None,
        observed_needs_escalation is not None,
        observed_domain,
        observed_intent,
        observed_posture,
        observed_proof_lane,
        observed_domain_lane,
        observed_human_contract,
    ])
    return {
        "schema": "harness.forum-route-receipt.route/v1",
        "route_id": route_id,
        "route_text_sha256": text_sha256(text),
        "route_text_bytes": len(text.encode("utf-8")),
        "route_text_preview": text[:180],
        "observation_status": "observed_route_frame" if observed else "route_text_only",
        "observed": observed,
        "observed_source": observed_source if observed else "",
        "observed_decided": observed_decided,
        "observed_confidence": observed_confidence,
        "observed_needs_escalation": observed_needs_escalation,
        "observed_domain": observed_domain,
        "observed_intent": observed_intent,
        "observed_posture": observed_posture,
        "observed_proof_lane": observed_proof_lane,
        "observed_domain_lane": observed_domain_lane,
        "observed_human_contract": observed_human_contract,
        "provider_execution_observed": False,
        "endpoint_probe_observed": False,
        "secret_policy": "route text and optional non-secret route-frame metadata only",
    }


def build_report(
    *,
    routes: list[str],
    observed_decided: str = "",
    observed_confidence: float | None = None,
    observed_needs_escalation: bool | None = None,
    observed_domain: str = "",
    observed_intent: str = "",
    observed_posture: str = "",
    observed_proof_lane: str = "",
    observed_domain_lane: str = "",
    observed_human_contract: str = "",
    observed_source: str = "forum.route",
) -> dict[str, Any]:
    rows = [
        route_row(
            route_id=f"route-{index:03d}",
            text=text,
            observed_decided=observed_decided,
            observed_confidence=observed_confidence,
            observed_needs_escalation=observed_needs_escalation,
            observed_domain=observed_domain,
            observed_intent=observed_intent,
            observed_posture=observed_posture,
            observed_proof_lane=observed_proof_lane,
            observed_domain_lane=observed_domain_lane,
            observed_human_contract=observed_human_contract,
            observed_source=observed_source,
        )
        for index, text in enumerate(routes, start=1)
    ]
    observed_confidences = [
        float(row["observed_confidence"])
        for row in rows
        if row["observed_confidence"] is not None
    ]
    return {
        "schema": "harness.forum-route-receipts/v1",
        "created_utc": utc_now(),
        "dependency_posture": "metadata-only; does not call Forum MCP or providers",
        "routes": rows,
        "summary": {
            "route_count": len(rows),
            "observed_route_frames": sum(1 for row in rows if row["observed"]),
            "route_text_only": sum(1 for row in rows if not row["observed"]),
            "escalation_count": sum(1 for row in rows if row["observed_needs_escalation"] is True),
            "mean_observed_confidence": round(sum(observed_confidences) / len(observed_confidences), 4)
            if observed_confidences else None,
            "domains": sorted({str(row["observed_domain"]) for row in rows if row["observed_domain"]}),
            "intents": sorted({str(row["observed_intent"]) for row in rows if row["observed_intent"]}),
            "proof_lanes": sorted({str(row["observed_proof_lane"]) for row in rows if row["observed_proof_lane"]}),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Forum route receipts",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Created UTC: `{report['created_utc']}`",
        f"- Dependency posture: {report['dependency_posture']}",
        f"- Routes: `{summary['route_count']}`",
        f"- Observed route frames: `{summary['observed_route_frames']}`",
        f"- Escalations: `{summary['escalation_count']}`",
        f"- Mean observed confidence: `{summary['mean_observed_confidence']}`",
        "",
        "| Route | Observation | Confidence | Escalation | Domain | Intent | Proof lane | Hash |",
        "|---|---|---:|---:|---|---|---|---|",
    ]
    for row in report["routes"]:
        lines.append(
            "| {route} | {status} | {confidence} | {escalation} | {domain} | {intent} | {proof} | `{hash}` |".format(
                route=row["route_id"],
                status=row["observation_status"],
                confidence="" if row["observed_confidence"] is None else row["observed_confidence"],
                escalation="" if row["observed_needs_escalation"] is None else str(row["observed_needs_escalation"]).lower(),
                domain=row["observed_domain"],
                intent=row["observed_intent"],
                proof=row["observed_proof_lane"],
                hash=row["route_text_sha256"][:16],
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


def _store_outputs(report: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="forum_route_receipts",
            body=report,
            run_id=run_id,
            verdict="FORUM_ROUTE_OBSERVED"
            if report["summary"]["observed_route_frames"]
            else "FORUM_ROUTE_TEXT_ONLY",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", action="append", default=[], help="route request text to receipt")
    parser.add_argument("--observed-decided", default="")
    parser.add_argument("--observed-confidence", type=float, default=None)
    parser.add_argument("--observed-needs-escalation", type=parse_bool, default=None)
    parser.add_argument("--observed-domain", default="")
    parser.add_argument("--observed-intent", default="")
    parser.add_argument("--observed-posture", default="")
    parser.add_argument("--observed-proof-lane", default="")
    parser.add_argument("--observed-domain-lane", default="")
    parser.add_argument("--observed-human-contract", default="")
    parser.add_argument("--observed-source", default="forum.route")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    routes = args.route or [
        "Route the active Codex/Flywheel local-model closed-loop harness objective.",
        "Route same-task Codex versus Flywheel versus Claude Code versus OpenCode benchmark comparison work.",
        "Route local 14B and 32B endpoint-readiness and release-gate work.",
    ]
    report = build_report(
        routes=routes,
        observed_decided=args.observed_decided,
        observed_confidence=args.observed_confidence,
        observed_needs_escalation=args.observed_needs_escalation,
        observed_domain=args.observed_domain,
        observed_intent=args.observed_intent,
        observed_posture=args.observed_posture,
        observed_proof_lane=args.observed_proof_lane,
        observed_domain_lane=args.observed_domain_lane,
        observed_human_contract=args.observed_human_contract,
        observed_source=args.observed_source,
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = _store_outputs(
        report,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "forum-route-receipts-json"),
            (md_path, "forum-route-receipts-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
