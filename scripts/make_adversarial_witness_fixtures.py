"""Create valid and adversarial byte-witness fixtures from a source packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _canonical_hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _recompute_packet_hash(packet: dict[str, Any]) -> dict[str, Any]:
    packet = json.loads(json.dumps(packet))
    packet.pop("packet_sha256", None)
    packet["packet_sha256"] = _canonical_hash(packet)
    return packet


def _load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _set_verdict(packet: dict[str, Any], verdict: str, failure_code: str) -> dict[str, Any]:
    updated = json.loads(json.dumps(packet))
    flywheel = updated.setdefault("flywheel", {})
    if not isinstance(flywheel, dict):
        flywheel = {}
        updated["flywheel"] = flywheel
    flywheel["verdict"] = verdict
    flywheel["failure_code"] = failure_code
    if verdict != "MATCH":
        witness = updated.setdefault("witness", {})
        if isinstance(witness, dict):
            witness["verification_attached"] = False
        verification = updated.setdefault("verification", {})
        if isinstance(verification, dict):
            verification["attempted"] = False
            verification["exit_code"] = None
    return _recompute_packet_hash(updated)


def make_fixtures(source: Path, out_dir: Path, prefix: str) -> dict[str, str]:
    packet = _load_packet(source)
    match_packet = _recompute_packet_hash(packet)
    unverifiable_packet = _set_verdict(
        packet,
        "UNVERIFIABLE",
        "fixture_missing_verification",
    )
    drift_packet = _set_verdict(
        packet,
        "DRIFT",
        "fixture_declared_drift",
    )
    tampered_packet = _recompute_packet_hash(packet)
    input_block = tampered_packet.setdefault("input", {})
    if isinstance(input_block, dict):
        input_block["receipt_sha256"] = "tampered-" + str(input_block.get("receipt_sha256", ""))[:24]
    corrupt_path = out_dir / f"{prefix}_corrupt.json"
    paths = {
        "match": str(out_dir / f"{prefix}_match.json"),
        "unverifiable": str(out_dir / f"{prefix}_unverifiable.json"),
        "drift": str(out_dir / f"{prefix}_drift.json"),
        "tampered_hash": str(out_dir / f"{prefix}_tampered_hash.json"),
        "corrupt": str(corrupt_path),
    }
    _write_json(Path(paths["match"]), match_packet)
    _write_json(Path(paths["unverifiable"]), unverifiable_packet)
    _write_json(Path(paths["drift"]), drift_packet)
    _write_json(Path(paths["tampered_hash"]), tampered_packet)
    corrupt_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_path.write_text("{ not-json: true", encoding="utf-8")
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--prefix", default="witness")
    args = parser.parse_args(argv)

    try:
        paths = make_fixtures(args.source, args.out_dir, args.prefix)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"witness fixture error: {exc}\n")
        return 2
    print(json.dumps({"schema": "adversarial-witness-fixtures/v1", "fixtures": paths}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
