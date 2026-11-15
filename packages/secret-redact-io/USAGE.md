# Usage

`secret-redact-io` wraps file reads, file writes, HTTP fetches, and subprocess
execution. Each operation redacts secrets (API keys, tokens, PEM private keys,
`password`/`api_key`-style fields) out of the returned text and produces a
hash-only `GuardrailReceipt` that records byte counts, SHA-256 hashes, status
metadata, and per-rule redaction counts -- but never the raw secret values.

## Install

`secret-redact-io` is not currently published on PyPI. Install from the GitHub
release tag or from a local checkout.

Pinned release tag:

```bash
python -m pip install "secret-redact-io @ git+https://github.com/HarperZ9/secret-redact-io.git@v0.1.0"
```

Local checkout for examples and tests:

```bash
git clone https://github.com/HarperZ9/secret-redact-io
cd secret-redact-io
python -m pip install -e ".[dev]"
```

Requires Python 3.10+. No third-party dependencies (stdlib only).

## CLI

The installed console script is `secret-redact-io`. It exposes four
subcommands: `read`, `write`, `fetch`, and `exec`. Pass `--json` to print the
full payload (text + receipt) as indented, key-sorted JSON; without `--json`
each non-receipt field is printed as `key: value`.

```
secret-redact-io read  <path> [--json]
secret-redact-io write <path> [--content TEXT | --from-file FILE] [--dry-run] [--json]
secret-redact-io fetch <url> [--timeout SECONDS] [--json]
secret-redact-io exec  [--timeout SECONDS] [--json] -- <command> [args...]
```

Notes:

- `write` takes the content either inline via `--content` or from a file via
  `--from-file`. With `--dry-run` nothing is written to disk; the receipt
  `operation` becomes `write.dry_run` and `metadata.written` is `false`.
- `exec` collects everything after `--` as the command to run. The leading `--`
  separator is stripped before execution.
- The same `python -m secret_redact_io ...` form works if the console script is
  not on your `PATH`.

## Python API

```python
from secret_redact_io import (
    read_text_guarded,
    write_text_guarded,
    fetch_guarded,
    run_guarded,
    GuardrailPolicy,
)
```

| Function | Signature (key args) | Returns |
| --- | --- | --- |
| `read_text_guarded` | `(path, *, policy=None)` | `GuardedTextResult` |
| `write_text_guarded` | `(path, content, *, dry_run=False, policy=None)` | `GuardedTextResult` |
| `fetch_guarded` | `(url, *, timeout=10, max_bytes=1_000_000, policy=None)` | `GuardedFetchResult` |
| `run_guarded` | `(argv, *, timeout=30, policy=None)` | `GuardedExecResult` |

Result objects are frozen dataclasses:

- `GuardedTextResult(text, receipt)`
- `GuardedFetchResult(text, status_code, receipt)`
- `GuardedExecResult(stdout, stderr, returncode, receipt)`

Every `receipt` is a `GuardrailReceipt` with `.to_dict()` and `.to_json()`.

You can also redact a string directly without any IO:

```python
from secret_redact_io import GuardrailPolicy

result = GuardrailPolicy.default().redact_text("token=ghp_" + "b" * 36)
# RedactionResult(text=..., counts={...}); result.total is the sum of counts
```

---

## Worked examples

> Output below is **illustrative**. The CLI/JSON outputs were captured on
> Python 3.12 (Windows); `created_at` and the SHA-256 hashes vary per run and
> per machine, and `\r\n` line endings in `exec` output are platform-specific.

### 1. Redact a string in memory (no IO)

```python
from secret_redact_io import GuardrailPolicy

result = GuardrailPolicy.default().redact_text("token=ghp_" + "b" * 36)
print(result.text)
print(result.counts)
print(result.total)
```

Expected output:

```
token=[REDACTED:github_token]
{'github_token': 1}
1
```

### 2. Read a file, get redacted text + receipt (CLI)

Create a file `sample.txt` with two secret-shaped lines. We build it by
concatenation so this document never embeds a contiguous secret literal -- the
same convention used in the other examples above:

```python
from pathlib import Path

# write_bytes (not write_text) so newlines stay LF on every platform -- the
# receipt below is for these exact 84 bytes.
Path("sample.txt").write_bytes(
    ("OPENAI_API_KEY=sk-" + "a" * 48 + "\n" + "password=hunter2\n").encode()
)
```

That is exactly 84 bytes -- an OpenAI-shaped key and a `password=` field, the
two redactions reported in the receipt below.

Run:

```bash
secret-redact-io read sample.txt --json
```

Expected output (hashes/timestamp will differ):

```json
{
  "receipt": {
    "created_at": "2026-06-18T17:16:25+00:00",
    "input_sha256": "be86b8194e49b4b9ab7772c6fec527e0379d85dae9281d076da020f5df9514d7",
    "metadata": {
      "exists": true
    },
    "operation": "read",
    "raw_bytes": 84,
    "redacted_bytes": 78,
    "redacted_sha256": "1505965ea1ad9be0550f30cfdcb94dda6ccc77c464161cfef90cdd5395e17276",
    "redactions": {
      "credential_field": 1,
      "openai_api_key": 1
    },
    "target": "sample.txt"
  },
  "text": "OPENAI_API_KEY=[REDACTED:openai_api_key]\npassword=[REDACTED:credential_field]\n"
}
```

### 3. Dry-run a write (nothing touches disk)

```bash
secret-redact-io write out.txt --content "note=hello password=hunter2" --dry-run --json
```

Expected output (hashes/timestamp will differ):

```json
{
  "receipt": {
    "created_at": "2026-06-18T17:16:38+00:00",
    "input_sha256": "c42e5abcd9baee427ec6b3af1ad2efe6d1c2ac8b2586c89c694a9cec8b3c0618",
    "metadata": {
      "written": false
    },
    "operation": "write.dry_run",
    "raw_bytes": 27,
    "redacted_bytes": 47,
    "redacted_sha256": "b32661ff881dc9acdbe3a0e4f0be5de7a3b9913f6141c12dbcd6374dd3d3dea7",
    "redactions": {
      "credential_field": 1
    },
    "target": "out.txt"
  },
  "text": "note=hello password=[REDACTED:credential_field]"
}
```

### 4. Run a subprocess with guarded output (Python API)

```python
from secret_redact_io import run_guarded

result = run_guarded(["python", "-c", "print('token=ghp_' + 'b' * 36)"])
print(result.returncode)
print(result.stdout.strip())
print(result.receipt.redactions)
```

Expected output:

```
0
token=[REDACTED:github_token]
{'github_token': 1}
```

The equivalent CLI form is:

```bash
secret-redact-io exec --json -- python -c "print('token=ghp_' + 'b' * 36)"
```

## What gets redacted

The default policy (`GuardrailPolicy.default()`) applies these rules, each
producing a labelled placeholder:

| Rule name | Placeholder |
| --- | --- |
| `private_key` | `[REDACTED:private_key]` |
| `openai_api_key` | `[REDACTED:openai_api_key]` |
| `github_token` | `[REDACTED:github_token]` |
| `aws_access_key` | `[REDACTED:aws_access_key]` |
| `jwt` | `[REDACTED:jwt]` |
| `bearer_token` | `Bearer [REDACTED:bearer_token]` |
| `credential_field` | `<field><sep><quote>[REDACTED:credential_field]<quote>` |

To customize, build your own `GuardrailPolicy([...])` and pass it via the
`policy=` keyword to any of the guarded functions.

## Troubleshooting

- `No matching distribution found for secret-redact-io`: the package is not on
  PyPI yet. Use the GitHub tag install or a local checkout.
- `secret-redact-io: command not found`: use `python -m secret_redact_io --help`
  or confirm that your virtual environment's scripts directory is on `PATH`.
- `fetch` examples touch the network. For offline checks, use `read`, `write
  --dry-run`, or `exec` with a local Python command.
