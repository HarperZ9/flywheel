# Usage Guide

`context-curator-lite` scans local text files (`.jsonl`, `.json`, `.md`,
`.txt`, `.log`) under one or more roots, extracts short planning-like
fragments that match its keyword set, heuristically redacts secret-shaped
values and direct identifiers, and writes a compact, sanitized context
bundle.

It can be driven from the command line (console script) or imported as a
Python module.

> Output blocks below are illustrative. The `generated` timestamp, the dated
> filenames, and the `*_sha256_prefix` / `root_sha256_prefixes` hash values
> depend on your run date and absolute paths, so they will differ on your
> machine.

## Install

`context-curator-lite` is not published on PyPI. The published v0.2.0 package is available from GitHub Releases. Install the wheel only after checking the release asset hash:

```bash
(
  set -eu
  wheel="context_curator_lite-0.2.0-py3-none-any.whl"
  curl -fL -o "$wheel" \
    https://github.com/HarperZ9/context-curator-lite/releases/download/v0.2.0/context_curator_lite-0.2.0-py3-none-any.whl
  python - "$wheel" <<'PY'
from pathlib import Path
import hashlib
import sys
expected = "e0323946afe9a075c4916759c70280987e57813d5fc6126cfdcbbfdeb6cf1556"
actual = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"wheel sha256 mismatch: {actual}")
PY
  python -m pip install "./$wheel"
)
```

The v0.2.0 sdist hash is `50bd0fa1fbb7efd34880c9538650b40647aab3f9ceb622aae8dec0b45f5c8958`. Requires Python 3.10+. The package has no runtime dependencies. If `pip install context-curator-lite` reports that no distribution was found, that is the current registry state rather than a local environment problem.

For source development, clone the repository and install it editable:

```bash
git clone https://github.com/HarperZ9/context-curator-lite.git
cd context-curator-lite
python -m pip install -e ".[test]"
python -m pytest
```

## Quickstart

```bash
mkdir -p notes artifacts
printf "%s\n" "Plan: verify install docs. TODO: cite source refs." > notes/plan.md
context-curator-lite --root notes --out-dir artifacts --telos-envelope
```

A successful run writes a dated Markdown summary, a dated JSONL bundle, `curated-session-context-manifest.json`, and, with `--telos-envelope`, `project-telos-context-envelope.json`.

## CLI

The installed console script is `context-curator-lite`. You can also invoke it
as a module: `python -m context_curator_lite`.

```
context-curator-lite --root ROOT [--root ROOT ...] --out-dir OUT_DIR
                     [--limit LIMIT] [--per-file-limit PER_FILE_LIMIT]
                     [--telos-envelope] [--version]
```

| Flag                | Type | Default | Meaning                                                        |
| ------------------- | ---- | ------- | -------------------------------------------------------------- |
| `--root`            | path | (req.)  | Root file or directory to scan. Repeat to scan multiple roots. |
| `--out-dir`         | path | (req.)  | Directory to write the bundle into (created if missing).       |
| `--limit`           | int  | `2500`  | Max total curated records across all files.                    |
| `--per-file-limit`  | int  | `12`    | Max curated records taken from any single file.                |
| `--telos-envelope`  | flag | -       | Also write `project-telos-context-envelope.json`.              |
| `--version`         | flag | -       | Print the version and exit.                                    |

On success the command writes three files into `--out-dir` and prints the
manifest JSON to stdout. Exit code is `0`.

Output files (the `<date>` is the run date, e.g. `2026-06-18`):

- `CURATED-SESSION-CONTEXT-<date>.md` -- human-readable summary + items.
- `curated-session-context-<date>.jsonl` -- one JSON record per curated fragment.
- `curated-session-context-manifest.json` -- run manifest (also printed to stdout).

### Example 1 -- scan the current directory

```bash
context-curator-lite --root . --out-dir ./artifacts
```

Pass `--telos-envelope` to also write
`project-telos-context-envelope.json`.

Expected stdout (illustrative):

```json
{
  "generated": "2026-06-18T10:16:39",
  "root_count": 1,
  "root_sha256_prefixes": [
    "6eba318fcdc6d539"
  ],
  "outputs": [
    "CURATED-SESSION-CONTEXT-2026-06-18.md",
    "curated-session-context-2026-06-18.jsonl",
    "curated-session-context-manifest.json"
  ],
  "absolute_paths_included": false,
  "raw_transcripts_copied": false,
  "source_files_scanned": 2,
  "raw_keyword_matches": 5,
  "curated_records": 4,
  "counts": {
    "next-action": 2,
    "blocker": 1,
    "idea": 1
  }
}
```

### Example 2 -- tighter caps and multiple roots

`--root` uses append semantics, so pass it more than once to scan several
locations in one run:

```bash
context-curator-lite \
  --root ./notes \
  --root ./logs \
  --out-dir ./artifacts \
  --limit 120 \
  --per-file-limit 8
```

The manifest's `root_count` becomes `2` and `root_sha256_prefixes` lists one
hash prefix per root.

### Telos context envelope export

```bash
context-curator-lite --root ./notes --out-dir ./artifacts --telos-envelope
```

The extra envelope uses the `project-telos.context-envelope/v1` shape. It is
compact for model input but lossless by reference: source refs carry relative
paths, full-file content hashes, and `gather docs ... --json` expansion
commands. It does not include absolute paths, raw transcripts, raw secret
values, or hidden payloads.

Illustrative excerpt:

```json
{
  "schema": "project-telos.context-envelope/v1",
  "compression": {
    "strategy": "heuristic_keyword_extract_with_hash_refs",
    "lossless_by_ref": true,
    "hidden_payloads_used": false
  },
  "source_refs": [
    {
      "id": "src_001",
      "path": "notes.md",
      "range": "full-file",
      "content_hash": "sha256:..."
    }
  ],
  "quality_gates": {
    "readability": "MATCH",
    "test_evidence": "UNVERIFIABLE",
    "freshness": "MATCH",
    "privacy": "MATCH"
  },
  "failure_code": null
}
```

### Example 3 -- inspect the JSONL bundle

```bash
context-curator-lite --root ./notes --out-dir ./artifacts
cat ./artifacts/curated-session-context-*.jsonl
```

Each line is one record (illustrative):

```json
{"kind": "next-action", "source": "session.jsonl", "source_sha256_prefix": "fc378a709b7d6f3a", "text": "resume the handoff: continue the roadmap for the repo"}
{"kind": "blocker", "source": "notes.md", "source_sha256_prefix": "754b6dc3f8728b19", "text": "blocker: the integration test failed on the worktree"}
{"kind": "idea", "source": "notes.md", "source_sha256_prefix": "754b6dc3f8728b19", "text": "architecture: design invariant for the curator whitepaper"}
```

`kind` is one of `next-action`, `blocker`, `idea`, `repo-context`, or
`context`. `source` is a path relative to the matched root (falling back to the
bare filename); absolute paths are never emitted.

## Python API

Import the `curator` submodule and call its functions. (Import the submodule
explicitly -- `from context_curator_lite import curator` -- rather than relying
on a top-level `main` re-export.)

```python
from context_curator_lite import curator

# Run the full pipeline (same work as the CLI).
exit_code = curator.main(
    roots=["./notes"],
    out_dir="./artifacts",
    limit=120,
    per_file_limit=8,
    telos_envelope=True,
)
assert exit_code == 0
```

`curator.main(roots, out_dir, limit=2500, per_file_limit=12, telos_envelope=False)`
writes the same base files described above, prints the manifest to stdout, and
returns `0`. Set `telos_envelope=True` to add
`project-telos-context-envelope.json`.

### Example 4 -- use the redaction / classification helpers directly

```python
from context_curator_lite import curator

curator.scrub("reach me at jane@example.com token=ghp_" + "A" * 36)
# -> 'reach me at <email> <redacted-secret>'

curator.classify("blocker: build failed")   # -> 'blocker'
curator.classify("architecture plan overview")  # -> 'idea'

curator.stable_id("notes.md")  # -> 16-char sha256 prefix, e.g. '754b6dc3f8728b19'
```

`scrub()` collapses whitespace, redacts secret-shaped substrings to
`<redacted-secret>`, replaces emails/IPs/URLs/hashes with `<email>`/`<ip>`/
`<url>`/`<hash>`, and truncates to 420 characters. `classify()` maps a fragment
to one of the `kind` labels. `stable_id()` returns a 16-character SHA-256
prefix.

## Caveats

- Redaction is heuristic, not a security boundary. Review bundles before sharing.
- Only the extensions `.jsonl`, `.json`, `.md`, `.txt`, `.log` are scanned.
- Files larger than 25 MiB are skipped; fragments under 20 characters (after
  scrubbing) are dropped, and duplicates are de-duplicated by content hash.
