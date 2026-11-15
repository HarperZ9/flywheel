"""`telos proof agent-action` -- the buyer-facing seam.

One command turns a trace + an authorization grant into an artifact folder:

    packet.json                 the unified, validated proof packet
    report.md                   the reviewer-facing report (trace vs receipt)
    crucible-thesis.json        \\ crucible's file contract, so an independent
    crucible-measurements.json  /  checker re-derives the verdict

Stdlib-only. No network, no third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .builder import build_agent_action_packet
from .packet import validate_agent_action_packet
from .._bundle import write_receipts
from .._crucible_peer import write_peer_assessment
from .report import render_report
from .verdicts import attach_verdicts, to_crucible_inputs


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _normalize_trace(raw: Any, trace_format: str) -> Any:
    if trace_format == "otel":
        from ..trace_adapters import normalize_otel

        return normalize_otel(raw)
    if trace_format == "langsmith":
        from ..trace_adapters import normalize_run_tree

        return normalize_run_tree(raw)
    return raw


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="telos proof agent-action",
        description="Turn an agent execution trace into a portable, re-checkable proof packet.",
    )
    p.add_argument("--trace", required=True, help="path to a trace export JSON")
    p.add_argument(
        "--trace-format",
        choices=("normalized", "otel", "langsmith"),
        default="normalized",
        help="trace input format: normalized (default), otel (OTLP/JSON), or langsmith (run tree)",
    )
    p.add_argument(
        "--authorization",
        required=True,
        help="path to an authorization-grant receipt JSON",
    )
    p.add_argument("--claim", required=True, help="the claim the packet asserts")
    p.add_argument(
        "--scope",
        required=True,
        help="the evidence boundary (what is / is not covered)",
    )
    p.add_argument("--packet-id", default="agent-action", help="packet identifier")
    p.add_argument("--out", default=".", help="output directory for the artifacts")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        raw_trace = _load_json(args.trace)
        authorization = _load_json(args.authorization)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: could not read input: {exc}", file=sys.stderr)
        return 2

    trace = _normalize_trace(raw_trace, args.trace_format)

    packet = attach_verdicts(
        build_agent_action_packet(
            trace,
            authorization,
            claim=args.claim,
            scope=args.scope,
            packet_id=args.packet_id,
        )
    )
    issues = validate_agent_action_packet(packet)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "packet.json").write_text(json.dumps(packet, indent=2), encoding="utf-8")
    report = render_report(packet)
    (out / "report.md").write_text(report, encoding="utf-8")
    thesis, measurements = to_crucible_inputs(packet)
    (out / "crucible-thesis.json").write_text(
        json.dumps(thesis, indent=2), encoding="utf-8"
    )
    (out / "crucible-measurements.json").write_text(
        json.dumps(measurements, indent=2), encoding="utf-8"
    )

    write_peer_assessment(out, thesis, measurements)
    write_receipts(out, domain="agent-action", packet_id=args.packet_id)
    print(report)
    if issues:
        print(f"\nPACKET INVALID: {len(issues)} issue(s)", file=sys.stderr)
        for issue in issues[:20]:
            print(f"  {issue.path}: {issue.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
