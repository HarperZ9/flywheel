"""`telos proof research-claim` -- pipeline-math++ CLI.

Turns a research input file (statement + sources + attempts + checks) into an
artifact folder: packet.json, report.md, and the crucible thesis/measurements for
independent re-derivation. A failed or unverifiable run still produces a valid,
useful packet. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .builder import build_research_claim_packet, to_crucible_inputs
from .packet import validate_research_claim_packet
from .._bundle import write_receipts
from .._crucible_peer import write_peer_assessment
from .report import render_report


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="telos proof research-claim",
        description="Turn a research claim + checks into a re-checkable proof packet.",
    )
    p.add_argument(
        "--input", required=True, help="JSON with statement, sources, attempts, checks"
    )
    p.add_argument("--claim", required=True, help="the claim the packet asserts")
    p.add_argument("--scope", required=True, help="the evidence boundary")
    p.add_argument("--packet-id", default="research-claim", help="packet identifier")
    p.add_argument("--out", default=".", help="output directory for the artifacts")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        spec = _load_json(args.input)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: could not read input: {exc}", file=sys.stderr)
        return 2

    packet = build_research_claim_packet(
        statement=spec.get("statement", ""),
        sources=spec.get("sources", []),
        attempts=spec.get("attempts", []),
        checks=spec.get("checks", []),
        claim=args.claim,
        scope=args.scope,
        packet_id=args.packet_id,
        uncertainty=spec.get("uncertainty"),
        promotion=spec.get("promotion"),
    )
    issues = validate_research_claim_packet(packet)

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
    write_receipts(out, domain="research-claim", packet_id=args.packet_id)
    print(report)
    if issues:
        print(f"\nPACKET INVALID: {len(issues)} issue(s)", file=sys.stderr)
        for issue in issues[:20]:
            print(f"  {issue.path}: {issue.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
