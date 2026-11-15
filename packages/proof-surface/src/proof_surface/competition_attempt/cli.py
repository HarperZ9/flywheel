"""`telos proof competition-attempt` -- competition/judge proof packet CLI.

Turns an input file (challenge + attempt + answer_extraction +
certificate_layers) into an artifact folder: packet.json, report.md, and the
crucible thesis/measurements. A packet with a forged judge pin, a fenced layer
without its probe, an inflated tier citation, an unchecked non-boxed
extraction, or a hermeticity contradiction is rejected. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .._bundle import write_receipts
from .._crucible_peer import write_peer_assessment
from .builder import build_competition_attempt_packet, to_crucible_inputs
from .packet import validate_competition_attempt_packet
from .report import render_report


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="telos proof competition-attempt",
        description=(
            "Turn a competition/judge attempt into a competition-attempt proof packet."
        ),
    )
    p.add_argument(
        "--input",
        required=True,
        help=(
            "JSON with sources, challenge, attempt, answer_extraction, "
            "certificate_layers"
        ),
    )
    p.add_argument("--claim", required=True, help="the claim the packet asserts")
    p.add_argument("--scope", required=True, help="the evidence boundary")
    p.add_argument(
        "--packet-id", default="competition-attempt", help="packet identifier"
    )
    p.add_argument("--out", default=".", help="output directory for the artifacts")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        spec = _load_json(args.input)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: could not read input: {exc}", file=sys.stderr)
        return 2

    packet = build_competition_attempt_packet(
        sources=spec.get("sources", []),
        challenge=spec.get("challenge", {}),
        attempt=spec.get("attempt", {}),
        answer_extraction=spec.get("answer_extraction", {}),
        certificate_layers=spec.get("certificate_layers", []),
        claim=args.claim,
        scope=args.scope,
        packet_id=args.packet_id,
        uncertainty=spec.get("uncertainty"),
    )
    issues = validate_competition_attempt_packet(packet)

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
    write_receipts(out, domain="competition-attempt", packet_id=args.packet_id)
    print(report)
    if issues:
        print(f"\nPACKET INVALID: {len(issues)} issue(s)", file=sys.stderr)
        for issue in issues[:20]:
            print(f"  {issue.path}: {issue.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
