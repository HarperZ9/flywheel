# IO Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean-room public Python SDK and CLI for guarded file, fetch, and subprocess IO with redacted outputs and hash-only audit receipts.

**Architecture:** The package exposes a small Python API around a shared redaction policy and receipt schema. Each IO wrapper returns a result object containing redacted user-facing content plus a JSON-serializable receipt that stores operation metadata, hashes, byte counts, exit status, and redaction counters without raw secret values.

**Tech Stack:** Python 3.10+, stdlib-only runtime, pytest for tests, setuptools build backend.

---

### Task 1: Redaction Policy

**Files:**
- Create: `src/secret_redact_io/redaction.py`
- Test: `tests/test_redaction.py`

- [ ] **Step 1: Write the failing test**

```python
from secret_redact_io import GuardrailPolicy


def test_redacts_common_secret_shapes_without_leaking_values() -> None:
    secret = "sk-" + ("a" * 48)
    text = f"OPENAI_API_KEY={secret}\nAuthorization: Bearer ghp_" + ("b" * 36)
    result = GuardrailPolicy.default().redact_text(text)
    assert secret not in result.text
    assert "ghp_" not in result.text
    assert result.total >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_redaction.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'secret_redact_io'`.

- [ ] **Step 3: Write minimal implementation**

Create `GuardrailPolicy.default()` and `redact_text()` with regex rules for common API keys, bearer tokens, JWTs, PEM private keys, password/token fields, and high-entropy values.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_redaction.py -q`
Expected: PASS.

### Task 2: Receipt Schema

**Files:**
- Create: `src/secret_redact_io/receipts.py`
- Test: `tests/test_receipts.py`

- [ ] **Step 1: Write the failing test**

```python
from secret_redact_io import GuardrailReceipt


def test_receipt_json_is_stable_and_hash_only() -> None:
    receipt = GuardrailReceipt.create(
        operation="read",
        target="sample.txt",
        raw_bytes=b"password=secret",
        redacted_text="password=[REDACTED:credential_field]",
        redactions={"credential_field": 1},
    )
    payload = receipt.to_json()
    assert "secret" not in payload
    assert '"operation": "read"' in payload
    assert len(receipt.input_sha256) == 64
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_receipts.py -q`
Expected: FAIL because `GuardrailReceipt` is missing.

- [ ] **Step 3: Write minimal implementation**

Use a dataclass with `create()`, `to_dict()`, and `to_json()` methods. Store hashes and counts, not raw input.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_receipts.py -q`
Expected: PASS.

### Task 3: File IO

**Files:**
- Create: `src/secret_redact_io/file_io.py`
- Test: `tests/test_file_io.py`

- [ ] **Step 1: Write the failing tests**

Tests cover guarded reads, dry-run writes, and default redaction before writes land on disk.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_file_io.py -q`
Expected: FAIL because `read_text_guarded` and `write_text_guarded` are missing.

- [ ] **Step 3: Write minimal implementation**

Implement UTF-8 text reads and atomic writes with `tempfile.NamedTemporaryFile`, `os.replace`, redacted result text, and receipts.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_file_io.py -q`
Expected: PASS.

### Task 4: Fetch And Exec Wrappers

**Files:**
- Create: `src/secret_redact_io/fetch_io.py`
- Create: `src/secret_redact_io/exec_io.py`
- Test: `tests/test_fetch.py`
- Test: `tests/test_exec.py`

- [ ] **Step 1: Write failing tests**

Use a local HTTP server for fetch and a Python one-liner subprocess for exec. Assert redacted outputs and receipt metadata.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch.py tests/test_exec.py -q`
Expected: FAIL because fetch and exec wrappers are missing.

- [ ] **Step 3: Write minimal implementation**

Use `urllib.request` with scheme/byte caps for fetch and `subprocess.run` with argv-only default for exec.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch.py tests/test_exec.py -q`
Expected: PASS.

### Task 5: CLI, Docs, And Release Gates

**Files:**
- Create: `src/secret_redact_io/cli.py`
- Create: `src/secret_redact_io/__main__.py`
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `LICENSE`
- Create: `.gitignore`
- Create: `.dockerignore`
- Create: `.env.example`
- Create: `scripts/check_public_surface.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_public_surface.py`

- [ ] **Step 1: Write failing tests**

Test `python -m secret_redact_io read`, `python -m secret_redact_io exec`, and the public surface scanner.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py tests/test_public_surface.py -q`
Expected: FAIL because CLI and scanner are missing.

- [ ] **Step 3: Write minimal implementation**

Expose `secret-redact-io` console script, JSON output, Markdown-friendly README, MIT license, CI workflow, and a scanner that blocks `.env` files, private path fragments, and secret-shaped literals.

- [ ] **Step 4: Run full verification**

Run:
```bash
python -m pytest
python scripts/check_public_surface.py
python -m build
```

Expected: all commands exit 0.
