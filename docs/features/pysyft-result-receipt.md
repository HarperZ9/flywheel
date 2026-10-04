# PySyft result receipt

A signed receipt for one approved PySyft job, which a person outside the run can check
with no access to the model or the data.

PySyft keeps a private model and private data hidden while an approved job runs. Since
PR #9536 (merged 2026-10-01), syft-job hashes a job when it arrives and when the data
owner approves it, and runs only a copy that matches the approved hash. That approved hash
is the hook this feature uses. The receipt binds a published score to exactly that job,
to the approval record PySyft wrote, and to the per-item rows the job released. Then it
signs the whole body.

## What a stranger can check

Given the receipt, the published job folder, the released `results.jsonl`, and the
signer's public key, `python -m harness.job_result_verify` checks:

| Check | What it catches |
|:--|:--|
| `job_hash` | The published job code is not the code that was approved. The hash is PySyft's own format, recomputed with the standard library. |
| `approval_covers_other_job` | The approval record names a different submission from the one that arrived. |
| `approver` | The approval names a reviewer the verifier does not accept. |
| `signature`, `claim_digest` | Any edit to the body after signing. The digest is recomputed from the body, never read from it. |
| `wrong_signer` | A body signed by a key other than the one the verifier pinned. |
| `results_bytes`, `items_root` | The released rows are not the rows the receipt sealed. |
| `score` | The claimed score does not recompute from the released rows. |
| `replay_nonce`, `replay_seen` | An old receipt presented for a new request. |
| `superstack:*`, `superstack_scene` | The embedded superstack receipt's seal, or its binding to the approved hash, does not hold. |
| `schema_or_limits` | A receipt that drops or rewords any of its fixed `does_not_prove` lines. |
| `reveal` | Once the hidden answers are revealed, a row's `correct` flag does not rescore. |

Verdicts are MATCH, DRIFT (naming every failed check), or UNVERIFIABLE when an input a
core check needs is missing. The attestation link is always reported as UNVERIFIABLE
beside the verdict, with the reason.

## The receipt

Schema `flywheel.pysyft-job-result/v1`, inside a `flywheel.signed-job-result/v1`
envelope. The body holds:

- `job`: `approved_hash` and `received_hash` as PySyft recorded them, the hash rule
  `pysyft-submission-hash/1`, and the PySyft source the format was read from.
- `approval`: `approved_by`, `approved_at`, `approval_method`, the review reason, the
  job status, and `record_sha256`, the SHA-256 of PySyft's `submission.json` bytes.
- `result`: the scoring rule `exact-match-strip/1`, an exact integer score
  (`correct` of `total`), `items_root` (an RFC 6962 style Merkle root over each row's
  canonical JSON), and `results_sha256`.
- `commitments`: SHA-256 values the data owner supplies for the hidden dataset and
  model. A stranger cannot open them.
- `attestation`: always `UNVERIFIABLE` in this version, with the gap named.
- `superstack`: a `superstack.receipt/1` (superstack 0.2.0). Its scene is the approved
  job; its content is the released results bytes. Its two verdicts are identity (do the
  bytes match) and tolerance (does the claimed score recompute from the rows).
- `nonce` and `receipt_id`: the requesting party's challenge, and a digest of the nonce,
  job and result, for replay checks.
- `does_not_prove`: the fixed list below.

The signature is Ed25519 over `claim_sha256`, the superstack canonical JSON SHA-256 of
the body. Verification needs only the Python standard library.

## The hash format

PySyft's `submission_hash` (in `packages/syft-job/src/syft_job/submission.py`) is
SHA-256 over every file in the job folder, in sorted relative-path order. Each file adds
its relative POSIX path in UTF-8, one zero byte, and the 32-byte SHA-256 of its contents.
The permission file `syft.pub.yaml` and folders such as `.venv` and `__pycache__` are
skipped. `harness/pysyft_job_hash.py` restates this without importing syft. On the real
run below, its value matched syft-job's own `submission_hash` and `code_hash` on the same
folder.

Two edges can differ, and both are stated in the module. PySyft sorts `Path` objects,
which on Windows fold case. PySyft's submitter-side `code_hash(as_sent=True)` normalizes
newlines. This module hashes raw bytes in POSIX order, the data owner's side, which is
the side that writes `approved_hash`.

## Run it

Rerun the real two-role flow on Linux or WSL:

```bash
git clone https://github.com/OpenMined/PySyft.git && cd PySyft
git checkout 36e65162ad2cfbae66d714db8d5c711e19a3a185
uv venv && . .venv/bin/activate
uv pip install ./packages/syft-migration ./packages/syft-perms \
  ./packages/syft-permissions ./packages/syft-job cryptography
cd /path/to/flywheel
python scripts/pysyft_receipt_demo.py --out bundle --nonce my-challenge
```

The demo runs both roles in one temporary SyftBox folder. The data owner holds 50
private addition items and a stand-in "model", a deliberately imperfect adder. The data
scientist submits a job that predicts each item and writes per-item rows. The data owner
approves the job and runs it through syft-job's runner, which checks the approved hash.
The demo then reads the finished job through `harness/pysyft_adapter.py`, builds and
signs the receipt with a fresh key whose private half is never written, verifies it,
and writes the bundle.

Check a bundle as an outsider:

```bash
python -m harness.job_result_verify --receipt bundle/receipt.json \
  --job-dir bundle/job --results bundle/results.jsonl \
  --public-key "$(cat bundle/public_key.hex)" --nonce my-challenge \
  --reviewer do@example.org --reveal bundle/reveal_answers.json
```

Exit codes: 0 for MATCH, 1 for DRIFT, 2 for UNVERIFIABLE.

## What ran, and where

- **Ran for real.** syft-job 0.1.41 built from PySyft commit `36e6516`, on Ubuntu 24.04
  under WSL with Python 3.12. The job was submitted, received, approved and run by
  syft-job itself. The approved hash in the receipt is the value syft-job wrote. The
  score was 40 of 50, and revealing the answers reproduced it exactly. That run's bundle
  is the test fixture in `tests/fixtures/pysyft_receipt/`.
- **Tamper tests.** `tests/test_job_result_receipt.py` runs 16 paired mutations on that
  bundle: a swapped job, an edited score, a forged approval, an approval of another
  submission, two replays, a wrong signer, a dropped row, a consistent lie in the rows,
  a dropped limit, and a broken superstack seal. Each pair asserts MATCH on the untouched
  bundle and DRIFT, naming the expected check, after the one change.
- **Not run.** No enclave and no attestation. No syft-enclave, syft-rds or multi-party
  flow. No network sync between two machines; both roles shared one folder.
- **Windows.** syft-job's arrival check did not pass on a Windows checkout in this test.
  The submitter declares a newline-normalized hash and the owner hashes raw bytes, so a
  CRLF file never leaves the `received` state. The Flywheel verifier itself runs on
  Windows.
- **PyPI.** syft-job 0.1.40 on PyPI predates PR #9536 and has no approved hash, so
  Flywheel declares no `pysyft` extra yet. Flywheel's core and the verifier never import
  syft. `harness/pysyft_adapter.py` works on a `JobClient` the caller already built.

## does_not_prove

These lines are fixed in `harness/job_result_receipt.py`. The verifier rejects a receipt
whose list differs from them by a word.

- It does not prove the hidden model or the hidden data were what the parties said;
  that needs the enclave attestation link, which this receipt does not carry.
- It does not prove the job ran only once, or that a run with a worse score was not
  discarded before this receipt was issued.
- It does not prove the reviewer read the code or judged it well; it binds the approval
  record PySyft wrote, and PySyft does not sign that record.
- It does not prove the scoring rule or the benchmark measures what it claims to.
- It does not prove the per-item rows are correct until the hidden answers are revealed
  and rescored; before that, the score is only consistent with the rows.
- It does not prove anything about enclave side channels, the hardware vendor, or any
  attestation verifier.
- A valid signature shows only that the key holder issued this body. It says nothing
  about whether the key holder is honest.

One test states the fifth line's consequence outright: a signer who lies consistently
in the rows passes every check until the answers are revealed.

## Licences

PySyft is Apache-2.0. Nothing from it is vendored. `harness/pysyft_job_hash.py` restates
the hash format and names its source file and commit. The superstack contract file is
vendored under its own FSL-1.1-MIT notice.
