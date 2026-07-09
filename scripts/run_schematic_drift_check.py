"""Check closed-loop integration schematics for metadata-only drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.schematic_drift import build_drift_report, load_json, render_markdown  # noqa: E402


DEFAULT_GRAPH = "C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json"
DEFAULT_REPORT = "C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md"


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def store_report(
    report: dict[str, Any],
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
            kind="schematic_drift_check",
            body=report,
            run_id=run_id,
            verdict=str(report.get("verdict", "SCHEMATIC_DRIFT_RECORDED")),
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default=DEFAULT_GRAPH)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--out", default="C:/tmp/schematic_drift_check.json")
    parser.add_argument("--markdown-out", default="C:/tmp/schematic_drift_check.md")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    graph_path = Path(args.graph)
    report_path = Path(args.report)
    graph = load_json(graph_path)
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    drift = build_drift_report(
        graph,
        graph_path=str(graph_path),
        report_text=report_text,
        report_path=str(report_path),
    )
    json_text = json.dumps(drift, indent=2, sort_keys=True)
    md_text = render_markdown(drift)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_report(
        drift,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "schematic-drift-check-json"),
            (md_path, "schematic-drift-check-markdown"),
        ],
    )
    if store_outputs:
        drift = {**drift, "store_outputs": store_outputs}
        json_text = json.dumps(drift, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
