"""CLI subcommand registration for `gather deconstruct`."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from gather.deconstruct.video_media_deconstruct import deconstruct_artifact
from gather.deconstruct.workflows import (
    civic_provenance_workflow,
    media_to_distill_workflow,
    research_to_verify_workflow,
)


def cmd_deconstruct(args: argparse.Namespace) -> int:
    path = Path(args.path)
    out_dir = Path(args.out) if args.out else None
    wf = args.workflow
    result: dict[str, Any]
    if wf == "auto":
        result = deconstruct_artifact(path, out_dir=out_dir)
    else:
        target_dir = out_dir or path.parent / f"{path.stem}_deconstruct"
        if wf == "media_to_distill":
            result = media_to_distill_workflow(path, target_dir)
        elif wf == "research_to_verify":
            result = research_to_verify_workflow(path, target_dir)
        else:
            result = civic_provenance_workflow(path, target_dir)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        verdict = (result.get("receipt") or {}).get("verdict", "UNVERIFIABLE")
        print(f"deconstruct {path.name}: workflow={wf} verdict={verdict}")
    return 0


def add_deconstruct_parser(sub: Any) -> None:
    p = sub.add_parser(
        "deconstruct",
        help="deterministically parse whitepapers, audio stems/mastering, video/images, or daylight sidecars",
    )
    p.add_argument("path", help="local file to deconstruct")
    p.add_argument("--out", default=None, metavar="DIR", help="output directory for stems, handoffs, and receipt")
    p.add_argument(
        "--workflow",
        default="auto",
        choices=["auto", "media_to_distill", "research_to_verify", "civic_provenance"],
        help="cohesive multimodal workflow runner (default: auto)",
    )
    p.add_argument("--json", action="store_true", help="emit full JSON output")
    p.set_defaults(func=cmd_deconstruct)
