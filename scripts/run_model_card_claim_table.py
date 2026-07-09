"""Generate a non-executing model-card claim table for benchmark model leads."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.model_card_claims import (  # noqa: E402
    DEFAULT_ARTIFACT_DIR,
    build_claim_table,
    file_sha256,
    load_json,
    render_markdown,
)


DEFAULT_CONTRACT = "C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json"


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def store_table(
    table: dict[str, Any],
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
            kind="model_card_claim_table",
            body=table,
            run_id=run_id,
            verdict="MODEL_CARD_CLAIM_TABLE_RECORDED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--evidence", default="")
    parser.add_argument("--artifact-dir", default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--out", default="C:/tmp/model_card_claim_table.json")
    parser.add_argument("--markdown-out", default="C:/tmp/model_card_claim_table.md")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    contract_path = Path(args.contract)
    contract = load_json(contract_path)
    evidence = {}
    evidence_path = ""
    evidence_sha256 = ""
    if args.evidence:
        evidence_file = Path(args.evidence)
        evidence = load_json(evidence_file)
        evidence_path = str(evidence_file)
        evidence_sha256 = file_sha256(evidence_file)
    table = build_claim_table(
        contract,
        contract_path=str(contract_path),
        contract_sha256=file_sha256(contract_path),
        evidence=evidence,
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
        artifact_dir=args.artifact_dir,
        run_id=args.run_id,
    )
    json_text = json.dumps(table, indent=2, sort_keys=True)
    md_text = render_markdown(table)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_table(
        table,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "model-card-claim-table-json"),
            (md_path, "model-card-claim-table-markdown"),
        ],
    )
    if store_outputs:
        table = {**table, "store_outputs": store_outputs}
        json_text = json.dumps(table, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
