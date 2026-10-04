# Canonical bytes: what a hash in this repository covers

Every sha256 this repository pins over a file covers the bytes Git stores for
that file (the blob). A checkout writes those same bytes on Linux, macOS and
Windows, whatever `core.autocrlf` says. This page records how that is enforced,
the choice made for each kind of artifact, and the published hashes that were
computed over converted bytes before the rule existed.

## Why this exists

Git for Windows defaults to `core.autocrlf=true`, which rewrites LF files to
CRLF on checkout. The bytes on disk then differ from the bytes Git stores, so a
stranger on Windows who ran `sha256sum` on a pinned file got a false DRIFT. Two
public claims failed this way on 2026-10-04: the Shapley placebo
preregistration (it pins `harness/shapley_far.py` and
`scripts/shapley_placebo_run.py` by their LF bytes) and the proof-surface
fixture behind closeout receipt 220 (pinned by its CRLF bytes, so it failed on
Linux instead). A fresh clone of `main` with `core.autocrlf=true` had 7537
files whose bytes differed from their blobs.

## The rule

`.gitattributes` starts with `* text=auto eol=lf`. For a text file committed
with LF, the checkout writes LF on every platform. Git leaves a file committed
with CRLF alone. Later lines override the default per path.

`tests/test_canonical_bytes.py` hashes every tracked file with
`git hash-object --no-filters` and requires each result to equal the blob id,
except for paths marked `eol=crlf`. CI runs it on Linux and on Windows with
`core.autocrlf` set to `true` and to `false` (`.github/workflows/recheck.yml`).

## The choice for each kind of artifact

| Artifact | Attribute | Why |
|---|---|---|
| Source, docs, JSON records, preregistrations (the default) | `text=auto eol=lf` | The checkout equals the blob, so a hash of the file on disk is the hash of the stored bytes. Editors on every platform handle LF. |
| Captured streams and hashed records (closeout `stdout.txt` and `stderr.txt`, the Shapley item set, which is stored with CRLF, and its run records) | `-text -diff` | The pinned digest covers the bytes as committed, CRLF included where present. `-text` keeps them byte for byte; normalizing would change what the pin means. |
| Fixtures hashed into receipts (`packs/**/fixtures`, `benchmarks/fixtures`, `tests/fixtures/pysyft_receipt`, superstack and raw-native vectors, the 1.3.0 records, the monitor gate set and spec in `harness/monitor_gate/data`) | `-text -diff` | A receipt binds these exact bytes. Treating them as binary also keeps a future CRLF edit from being silently normalized on commit. |
| Windows scripts (`*.ps1`, `*.cmd`, `*.bat`) | `text eol=crlf` | They must be CRLF to run under cmd. None is pinned by hash, and the gate test skips them. |
| Generated artwork, Flutter registrants, shader sources, desktop payload notices | `text eol=lf` | Already pinned to LF before this rule; kept as written. |
| Binary files | Git's own detection | Unchanged. |

## Verifying a pin

```bash
python -m harness.canonical_bytes check PATH SHA256            # the file on disk
python -m harness.canonical_bytes check PATH SHA256 --rev REV  # the blob Git stores
python -m harness.prereg_pins project-docs/prereg/2026-10-04-shapley-placebo.md
```

The result is MATCH only for the exact bytes. When the bytes differ only in line
endings the verdict is `EOL_ONLY` (exit 3), with the form that matched and how to
get the stored bytes. It never reports MATCH for a converted form, so no check
became weaker. Code that builds pinned artifacts reads blobs through Git already:
`scripts/_lane_payload_source.py`, `scripts/source_tool_provenance.py` and
`scripts/check_bundled_lane_descriptors.py` use `git cat-file`.

## Published hashes computed over CRLF bytes

A survey on 2026-10-04 hashed every tracked text file three ways (raw, LF form,
CRLF form) and matched every 64-character hex string in the repository against
them. These published values equal the CRLF form of a file Git stores with LF.
They were computed on a Windows checkout before the rule. Their meaning is
unchanged: each is the sha256 of the CRLF form of that blob, and none was
rewritten. `python -m harness.canonical_bytes check PATH SHA256` reports
`EOL_ONLY` with `matched_form: crlf` for each, which is the expected result.

| Where the value is published | File it covers | Values |
|---|---|---|
| `demos/index.json` (`transcript_sha256`, written by `scripts/build_demos_index.py`) | `demos/*/transcript.json` | 10 |
| `handoff/site-designer/MANIFEST.sha256` | `artifacts/flywheel-local-coder-14b-benchmark-ci.json`, `handoff/site-designer/evidence/benchmark-ci.json` | 2 |
| `project-docs/records/2026-08-14-desktop-phase-2-journey-flutter.md` | `desktop/lib/models/journey_models.dart`, `desktop/test/journey_controller_test.dart` | 2 |
| `project-docs/records/2026-08-14-desktop-phase-3-truth-safety.md` | `desktop/lib/widgets/system_text_scaler.dart` | 1 |
| `project-docs/records/search-effort-gate/RUN-LOG.md` | `live-hard.json`, `live-hard_v2.json` in the same directory | 2 |
| `desktop/lib/assistant/rowan_action_cue_pack_provenance.dart` | the complete pack `manifest.json` | 1 |

No test or verifier compares these values with the files today, so none of them
failed. Regenerating `demos/index.json` now writes LF digests; that would be a new
value with a new basis, and the change would need its own dated note here.

## What this does not prove

- That every pinned hash in the repository was found. The survey matches values
  that equal a current file; a pin over a file that has since changed does not
  show up, and its basis is not recorded.
- Anything about other repositories. The sealed witness repositories carry their
  own `.gitattributes` that mark sealed files `-text`.
