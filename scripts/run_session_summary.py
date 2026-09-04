"""Emit a four-question run summary with derived evidence and stated claims kept apart."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.session_summary import SCOPES, build_session_summary, render_markdown  # noqa: E402


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def load_statements(args: argparse.Namespace) -> dict:
    """Stated answers, from a JSON file and from repeatable flags."""
    statements: dict[str, list[str]] = {}
    if args.statements:
        loaded = json.loads(Path(args.statements).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("statements file must hold an object keyed by question")
        statements.update({key: list(value) for key, value in loaded.items()})
    for key, values in (("intent", args.intent), ("did", args.did),
                        ("remaining", args.remaining), ("decisions", args.decision)):
        # An explicit empty flag is how a caller claims nothing is left, and that
        # claim is exactly what the disagreement check tests against the tree.
        if values is not None:
            statements[key] = [item for item in values if item != ""]
    return statements


def store_summary(summary: dict, *, store_root: str, run_id: str,
                  artifacts: list[tuple[str, str]]) -> list[dict]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [store.put_receipt(kind="session_summary", body=summary, run_id=run_id,
                                 verdict=str(summary.get("verdict", "SUMMARY_RECORDED")))]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def strict_exit(summary: dict) -> int:
    """The three-outcome exit, the same vocabulary the output check uses.

    1 is a contradiction: a stated answer claims more than the tree supports.
    3 is unfinished rather than wrong, which is a different fact and must not
    be reported as a clean run. 0 is a run with nothing outstanding.
    """
    if summary["disagreements"]:
        return 1
    remaining = [answer for answer in summary["answers"] if answer["key"] == "remaining"]
    return 3 if (remaining and remaining[0]["derived"]) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--scope", choices=SCOPES, default="session")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--base", default="", help="ref the branch is measured against")
    parser.add_argument("--since", default="", help="ISO timestamp bounding session-scope receipts")
    parser.add_argument("--receipt-store", default="", help="store root read for session-scope receipts")
    parser.add_argument("--validation-ledger", default="",
                        help="output-validation ledger folded into what is left to finish")
    parser.add_argument("--statements", default="", help="JSON file of stated answers")
    parser.add_argument("--intent", action="append")
    parser.add_argument("--did", action="append")
    parser.add_argument("--remaining", action="append")
    parser.add_argument("--decision", action="append")
    parser.add_argument("--out", default="C:/tmp/session_summary.json")
    parser.add_argument("--markdown-out", default="C:/tmp/session_summary.md")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--fail-on-disagreement", action="store_true",
                        help="exit non-zero when a stated answer claims more than the tree supports")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 on a disagreement and 3 while anything is outstanding")
    args = parser.parse_args(argv)

    summary = build_session_summary(Path(args.root), scope=args.scope, base=args.base,
                                    since=args.since, store_root=args.receipt_store,
                                    validation_ledger=args.validation_ledger,
                                    statements=load_statements(args))
    json_text = json.dumps(summary, indent=2, sort_keys=True)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, render_markdown(summary))
    store_outputs = store_summary(summary, store_root=args.store_root, run_id=args.run_id,
                                  artifacts=[(json_path, "session-summary-json"),
                                             (md_path, "session-summary-markdown")])
    if store_outputs:
        summary = {**summary, "store_outputs": store_outputs}
        json_text = json.dumps(summary, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    if args.strict:
        return strict_exit(summary)
    return 1 if (args.fail_on_disagreement and summary["disagreements"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
