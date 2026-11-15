from __future__ import annotations

import argparse

from . import __version__
from . import curator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a sanitized context bundle from planning artifacts."
    )
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--limit", type=int, default=2500)
    parser.add_argument("--per-file-limit", type=int, default=12)
    parser.add_argument(
        "--telos-envelope",
        action="store_true",
        help="also write project-telos-context-envelope.json",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return curator.main(
        args.root,
        args.out_dir,
        args.limit,
        args.per_file_limit,
        args.telos_envelope,
    )


if __name__ == "__main__":
    raise SystemExit(main())
