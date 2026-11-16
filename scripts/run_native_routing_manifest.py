"""Expand a native routing task-family set into planned-only artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.native_routing_manifest import (  # noqa: E402
    DEFAULT_ARTIFACT_DIR,
    build_manifest,
    file_sha256,
    load_json,
    render_case_projection,
    render_markdown,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TASK_SET = ROOT / "benchmarks" / "fixtures" / "native-routing-task-family-demo-v1.json"


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def write_projection_files(doc: dict, projection_dir: Path) -> list[str]:
    written: list[str] = []
    if not projection_dir:
        return written
    for case in doc["cases"]:
        for arm in doc["candidate_arms"]:
            projection = render_case_projection(doc, case, arm)
            base = projection_dir / case["case_id"] / arm["arm_id"]
            written.append(write_text(base / "model_visible_prompt.txt", projection["model_visible_prompt"]))
            written.append(write_text(
                base / "model_visible_features.json",
                json.dumps(projection["model_visible_features"], indent=2, sort_keys=True) + "\n",
            ))
            written.append(write_text(
                base / "cache_key_material.json",
                json.dumps(projection["cache_key_material"], indent=2, sort_keys=True) + "\n",
            ))
            written.append(write_text(
                base / "hidden_authority_manifest.json",
                json.dumps(projection["hidden_authority_manifest"], indent=2, sort_keys=True) + "\n",
            ))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-set", default=str(DEFAULT_TASK_SET))
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--out", default="native_routing_manifest.json")
    parser.add_argument("--markdown-out", default="native_routing_manifest.md")
    parser.add_argument("--projection-dir", default="")
    args = parser.parse_args(argv)

    task_set_path = Path(args.task_set)
    doc = load_json(task_set_path)
    manifest = build_manifest(
        doc,
        source_path=str(task_set_path),
        source_sha256=file_sha256(task_set_path),
        artifact_dir=args.artifact_dir,
    )
    if args.projection_dir:
        manifest["projection_files"] = write_projection_files(doc, Path(args.projection_dir))
    write_text(Path(args.out), json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    write_text(Path(args.markdown_out), render_markdown(manifest))
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
