#!/usr/bin/env python3
# Best-effort demo -- not runtime-verified by author.
"""End-to-end demo of secret-redact-io's public API.

Exercises in-memory redaction, guarded read, guarded (dry-run) write, and
guarded subprocess execution. Run with:

    python examples/demo.py

No network call is made; fetch_guarded is documented but intentionally not
exercised here so the demo stays offline and deterministic.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from secret_redact_io import (
    GuardrailPolicy,
    read_text_guarded,
    run_guarded,
    write_text_guarded,
)


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    openai_key = "sk-" + ("a" * 48)
    github_token = "ghp_" + ("b" * 36)

    # 1. In-memory redaction, no IO.
    section("redact_text (in memory)")
    policy = GuardrailPolicy.default()
    redacted = policy.redact_text(f"token={github_token}\npassword=hunter2")
    print("text:  ", redacted.text.replace("\n", " | "))
    print("counts:", redacted.counts)
    print("total: ", redacted.total)

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        # 2. Guarded read of a file containing a secret.
        section("read_text_guarded")
        sample = tmpdir / "sample.txt"
        sample.write_text(f"OPENAI_API_KEY={openai_key}\n", encoding="utf-8")
        read_result = read_text_guarded(sample)
        assert openai_key not in read_result.text
        print("text:    ", read_result.text.strip())
        print("operation:", read_result.receipt.operation)
        print("redactions:", read_result.receipt.redactions)

        # 3. Guarded write in dry-run mode (nothing is written to disk).
        section("write_text_guarded (dry_run=True)")
        target = tmpdir / "out.txt"
        write_result = write_text_guarded(
            target, "api_key: abc123456789", dry_run=True
        )
        print("text:    ", write_result.text)
        print("operation:", write_result.receipt.operation)
        print("written: ", write_result.receipt.to_dict()["metadata"]["written"])
        print("file exists on disk:", target.exists())

    # 4. Guarded subprocess execution.
    section("run_guarded")
    exec_result = run_guarded(
        [sys.executable, "-c", f"print('token={github_token}')"]
    )
    assert github_token not in exec_result.stdout
    print("returncode:", exec_result.returncode)
    print("stdout:    ", exec_result.stdout.strip())
    print("redactions:", exec_result.receipt.redactions)

    section("receipt as JSON")
    print(exec_result.receipt.to_json())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
