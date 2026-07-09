"""Generate a metadata-only adapter/runtime compatibility matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.adapter_runtime_matrix import (  # noqa: E402
    DEFAULT_CONTRACT,
    build_matrix,
    file_sha256,
    load_json,
    render_markdown,
)
from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _optional_json(path_text: str) -> tuple[dict[str, Any], str, str]:
    if not path_text:
        return {}, "", ""
    path = Path(path_text)
    if not path.exists():
        return {}, str(path), ""
    return load_json(path), str(path), file_sha256(path)


def store_matrix(
    matrix: dict[str, Any],
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
            kind="adapter_runtime_matrix",
            body=matrix,
            run_id=run_id,
            verdict="ADAPTER_RUNTIME_MATRIX_RECORDED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    parser.add_argument("--endpoint-profiles", default="")
    parser.add_argument("--endpoint-auth-status", default="")
    parser.add_argument("--out", default="C:/tmp/adapter_runtime_matrix.json")
    parser.add_argument("--markdown-out", default="C:/tmp/adapter_runtime_matrix.md")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    contract_path = Path(args.contract)
    contract = load_json(contract_path)
    endpoint_profiles, endpoint_profiles_path, endpoint_profiles_sha256 = _optional_json(args.endpoint_profiles)
    endpoint_auth, endpoint_auth_path, endpoint_auth_sha256 = _optional_json(args.endpoint_auth_status)
    matrix = build_matrix(
        contract,
        contract_path=str(contract_path),
        contract_sha256=file_sha256(contract_path),
        endpoint_profiles=endpoint_profiles,
        endpoint_profiles_path=endpoint_profiles_path,
        endpoint_profiles_sha256=endpoint_profiles_sha256,
        endpoint_auth_status=endpoint_auth,
        endpoint_auth_status_path=endpoint_auth_path,
        endpoint_auth_status_sha256=endpoint_auth_sha256,
        run_id=args.run_id,
    )
    json_text = json.dumps(matrix, indent=2, sort_keys=True)
    md_text = render_markdown(matrix)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_matrix(
        matrix,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "adapter-runtime-matrix-json"),
            (md_path, "adapter-runtime-matrix-markdown"),
        ],
    )
    if store_outputs:
        matrix = {**matrix, "store_outputs": store_outputs}
        json_text = json.dumps(matrix, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
