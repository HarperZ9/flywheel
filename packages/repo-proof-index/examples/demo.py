#!/usr/bin/env python3
# Best-effort demo -- not runtime-verified by author.
"""End-to-end demo of repo-proof-index against the bundled example contracts.

Exercises the real public API (load_rows, format_table, summarize_rows,
format_summary, summarize_contract) and the real CLI entry point
(repo_proof_index.cli.main), using only functions and flags that exist in
the current source.

Run from the repository root:

    python examples/demo.py

If you have an editable/dev install (`pip install -e ".[test]"`) you can run
it from anywhere; otherwise this script adds ./src to sys.path so it works
straight from a clone.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from repo_proof_index import format_table, load_rows, summarize_contract  # noqa: E402
from repo_proof_index.cli import main as cli_main  # noqa: E402
from repo_proof_index.indexer import format_summary, summarize_rows  # noqa: E402

CONTRACTS_DIR = REPO_ROOT / "examples" / "contracts"
MALFORMED = REPO_ROOT / "examples" / "malformed" / "not-object.json"


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    contract_files = sorted(CONTRACTS_DIR.glob("*.json"))

    # 1. Index a single contract into one ProofRow.
    banner("summarize_contract: one file -> one ProofRow")
    row = summarize_contract(
        CONTRACTS_DIR / "sample-product-usecase.json", CONTRACTS_DIR
    )
    print(row)

    # 2. Index every bundled contract and render the table.
    banner("load_rows + format_table: all bundled contracts")
    rows = load_rows(contract_files, root=REPO_ROOT)
    print(format_table(rows))

    # 3. Roll the same rows up into a release-readiness summary.
    banner("summarize_rows + format_summary: release-readiness view")
    summary = summarize_rows(rows)
    print(format_summary(summary))

    # 4. Drive the real CLI the same way an installed console script would.
    banner("cli.main: JSON rows for one contract")
    cli_main([str(CONTRACTS_DIR / "sample-product-usecase.json"), "--json"])

    banner("cli.main: validate a proof-surface packet")
    validate_code = cli_main(
        ["--validate", str(CONTRACTS_DIR / "proof-surface-packet.json")]
    )
    print(f"validate exit code: {validate_code}")

    banner("cli.main: malformed input reports an error and exits non-zero")
    error_code = cli_main([str(MALFORMED)])
    print(f"malformed exit code: {error_code}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
