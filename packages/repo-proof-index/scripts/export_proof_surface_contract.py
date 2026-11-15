#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "dist" / "proof-surface-contract-v0.1"

CONTRACT_FILES = (
    "docs/PROOF-SURFACE-PACKET-v0.1.md",
    "docs/PROOF-SURFACE-INTEROP.md",
    "docs/PROOF-SURFACE-REGISTRY.json",
    "schemas/proof-surface-packet.schema.json",
    "conformance/proof-surface/v0.1/manifest.json",
    "conformance/proof-surface/v0.1/README.md",
    "conformance/proof-surface/v0.1/valid/minimal.packet.json",
    "conformance/proof-surface/v0.1/invalid/unknown-root-field.packet.json",
    "conformance/proof-surface/v0.1/invalid/bad-check-status.packet.json",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export the proof-surface v0.1 contract bundle."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory for the portable contract bundle.",
    )
    return parser


def copy_contract_file(relative_path: str, out_dir: Path) -> None:
    source = ROOT / relative_path
    if not source.is_file():
        raise FileNotFoundError(f"contract source missing: {relative_path}")
    target = out_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def write_index(out_dir: Path) -> None:
    index = out_dir / "BUNDLE.md"
    files = "\n".join(f"- `{path}`" for path in CONTRACT_FILES)
    index.write_text(
        "\n".join(
            [
                "# Proof Surface Contract Bundle v0.1",
                "",
                "Portable copy of the proof-surface packet v0.1 contract.",
                "",
                "This bundle is an evidence-carrier contract. It is not a",
                "trust, safety, authorization, compliance, or certification",
                "verdict.",
                "",
                "## Files",
                "",
                files,
                "",
            ]
        ),
        encoding="utf-8",
    )


def export_contract(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for relative_path in CONTRACT_FILES:
        copy_contract_file(relative_path, out_dir)
    write_index(out_dir)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        export_contract(args.out)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
