"""`telos proof control-certificate` -- decrease/stability certificate CLI.

Turns an input file (system + certificate + witnesses + negative_fixture +
sim_to_real) into an artifact folder: packet.json, report.md, and the crucible
thesis/measurements. A packet whose negative fixture cannot violate the
certificate, whose kind is missing a required condition, or whose hardware
claim lacks hardware evidence is rejected. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .._bundle import write_receipts
from .._crucible_peer import write_peer_assessment
from .builder import build_control_certificate_packet, to_crucible_inputs
from .packet import validate_control_certificate_packet
from .report import render_report


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="telos proof control-certificate",
        description=(
            "Turn a stability/feasibility claim into a control-certificate "
            "proof packet."
        ),
    )
    p.add_argument(
        "--input",
        required=True,
        help=(
            "JSON with system, certificate, witnesses, negative_fixture, "
            "sim_to_real, sources"
        ),
    )
    p.add_argument("--claim", required=True, help="the claim the packet asserts")
    p.add_argument("--scope", required=True, help="the evidence boundary")
    p.add_argument(
        "--packet-id", default="control-certificate", help="packet identifier"
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

    packet = build_control_certificate_packet(
        sources=spec.get("sources", []),
        system=spec.get("system", {}),
        certificate=spec.get("certificate", {}),
        witnesses=spec.get("witnesses", []),
        negative_fixture=spec.get("negative_fixture", {}),
        trajectory=spec.get("trajectory", {}),
        claim=args.claim,
        scope=args.scope,
        packet_id=args.packet_id,
        sim_to_real=spec.get("sim_to_real"),
        uncertainty=spec.get("uncertainty"),
    )
    issues = validate_control_certificate_packet(packet)

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
    write_receipts(out, domain="control-certificate", packet_id=args.packet_id)
    print(report)
    if issues:
        print(f"\nPACKET INVALID: {len(issues)} issue(s)", file=sys.stderr)
        for issue in issues[:20]:
            print(f"  {issue.path}: {issue.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
