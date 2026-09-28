"""Write a Studio body runtime source-basis manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.studio_body_runtime_manifest import build_studio_body_runtime_manifest


def main() -> int:
    args = _parser().parse_args()
    doc = build_studio_body_runtime_manifest(
        studio_engine_src=_optional(args.studio_engine_src),
        accountable_surface_src=_optional(args.accountable_surface_src),
        coherence_membrane_src=_optional(args.coherence_membrane_src),
        proof_surface_src=_optional(args.proof_surface_src),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--studio-engine-src", type=Path)
    parser.add_argument("--accountable-surface-src", type=Path)
    parser.add_argument("--coherence-membrane-src", type=Path)
    parser.add_argument("--proof-surface-src", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _optional(value: Path | None) -> Path | None:
    return value if value is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
