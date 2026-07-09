"""Expand the custom agentic task set into a non-executing benchmark manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.agentic_task_manifest import (  # noqa: E402
    DEFAULT_ARTIFACT_DIR,
    build_manifest,
    file_sha256,
    load_json,
    render_markdown,
    split_csv,
)
from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


DEFAULT_TASK_SET = "C:/dev/local-model/benchmarks/agentic-task-set-v1.json"
DEFAULT_ADAPTER = "C:/dev/local-model/benchmarks/agentic-task-set-adapter-v1.json"


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def store_manifest(
    manifest: dict[str, Any],
    *,
    store_root: str,
    run_id: str,
    artifacts: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="agentic_task_manifest",
            body=manifest,
            run_id=run_id,
            verdict="AGENTIC_TASK_MANIFEST_RECORDED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-set", default=DEFAULT_TASK_SET)
    parser.add_argument("--adapter", default=DEFAULT_ADAPTER)
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--provider-roles", default="dry")
    parser.add_argument("--out", default="C:/tmp/agentic_task_manifest.json")
    parser.add_argument("--markdown-out", default="C:/tmp/agentic_task_manifest.md")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    task_set_path = Path(args.task_set)
    adapter_path = Path(args.adapter)
    task_set = load_json(task_set_path)
    adapter = load_json(adapter_path)
    manifest = build_manifest(
        task_set,
        adapter,
        run_id=args.run_id,
        artifact_dir=args.artifact_dir,
        provider_roles=split_csv(args.provider_roles) or ["dry"],
        task_set_path=str(task_set_path),
        adapter_path=str(adapter_path),
        task_set_sha256=file_sha256(task_set_path),
        adapter_sha256=file_sha256(adapter_path),
    )
    json_text = json.dumps(manifest, indent=2, sort_keys=True)
    md_text = render_markdown(manifest)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_manifest(
        manifest,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "agentic-task-manifest-json"),
            (md_path, "agentic-task-manifest-markdown"),
        ],
    )
    if store_outputs:
        manifest = {**manifest, "store_outputs": store_outputs}
        json_text = json.dumps(manifest, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
