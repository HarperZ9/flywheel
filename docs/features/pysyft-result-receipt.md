# PySyft result receipt

A signed receipt for one approved PySyft job, which a person outside the run can check
from the receipt alone, while the model and the data stay private.

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
| `key_id` | A `signature.key_id` that is not the id of the pinned key (`ed25519:` and the first 32 hex of the key's SHA-256). The field sits outside the signed body, so the verifier derives it rather than trusting it. |
| `envelope_schema` | An envelope whose `schema` is not `flywheel.signed-job-result/v1`. This field also sits outside the signed body. |
| `results_bytes`, `items_root` | The released rows are not the rows the receipt sealed. |
| `score` | The claimed score does not recompute from the released rows. |
| `receipt_id` | A `receipt_id` that does not recompute from the body's nonce, job and result. A signer who rebuilds a result and leaves the old id, or forges a fresh one, is caught here. |
| `replay_nonce`, `replay_seen` | An old receipt presented for a new request. The seen-list is keyed on the recomputed id. |
| `superstack:*`, `superstack_scene` | The embedded superstack receipt's seal, or its binding to the approved hash, does not hold. |
| `schema_or_scope` | A receipt that drops or rewords any of its fixed `scope` lines. |
| `reveal` | Once the hidden answers are revealed, a row's `correct` flag does not rescore. |

Verdicts are MATCH, DRIFT (naming every failed check), or UNVERIFIABLE when an input a
core check needs is missing. The attestation link is always reported as UNVERIFIABLE
beside the verdict, with the reason.

## The receipt

Schema `flywheel.pysyft-job-result/v2`, inside a `flywheel.signed-job-result/v1`
envelope. The body holds:

- `job`: `approved_hash` and `received_hash` as PySyft recorded them, the hash rule
  `pysyft-submission-hash/1`, and the PySyft source the format was read from.
- `approval`: `approved_by`, `approved_at`, `approval_method`, the review reason, the
  job status, and `record_sha256`, the SHA-256 of PySyft's `submission.json` bytes.
- `result`: the scoring rule `exact-match-strip/1`, an exact integer score
  (`correct` of `total`), `items_root` (an RFC 6962 style Merkle root over each row's
  canonical JSON), and `results_sha256`.
- `commitments`: SHA-256 values the data owner supplies for the hidden dataset and
  model, opened later by the owner.
- `attestation`: always `UNVERIFIABLE` in this version, with the gap named.
- `superstack`: a `superstack.receipt/1` (superstack 0.2.0). Its scene is the approved
  job; its content is the released results bytes. Its two verdicts are identity (do the
  bytes match) and tolerance (does the claimed score recompute from the rows).
- `nonce` and `receipt_id`: the requesting party's challenge, and the superstack
  canonical SHA-256 of `{nonce, job, result}`, for replay checks. The verifier
  recomputes the id and compares it with the recorded one.
- `scope`: the fixed list below.

The signature is Ed25519 over `claim_sha256`, the superstack canonical JSON SHA-256 of
the body. The envelope's `schema` and the signature's `key_id` sit outside that body, so
the verifier checks each against a value it derives: the fixed envelope schema, and the
id of the key it pinned. Verification needs only the Python standard library.

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
- **Tamper tests.** `tests/test_job_result_receipt.py` runs 21 paired mutations on that
  bundle: a swapped job, an edited score, a forged approval, an approval of another
  submission, two replays, a wrong signer, a dropped row, a consistent lie in the rows,
  the same lie with a stale `receipt_id`, a forged `receipt_id`, a relabelled `key_id`,
  an attacker key under the pinned key's id, a relabelled envelope schema, a dropped
  limit, and a broken superstack seal. Each pair asserts MATCH on the untouched bundle
  and DRIFT, naming the expected check, after the one change. A further test flips every
  byte of the envelope `schema` and `key_id` one bit at a time and asserts DRIFT on each.
- **Byte sweep.** Flipping the low bit of each of the 5,744 bytes of the fixture's
  `receipt.json` gives 1,315 files that no longer parse. Before these two checks the
  verifier returned MATCH on 81 of the rest: 69 flips in the values of the envelope
  `schema` and `signature.key_id`, and 12 in those two key names, which drop the field. With the `key_id` and `envelope_schema` checks it returns MATCH on
  none. The gap was found by an independent in-browser re-derivation of this verifier.
- **Test scope.** One machine, both roles sharing one folder. Enclave attestation,
  syft-enclave, syft-rds, multi-party flows and network sync between machines are
  the next tests to run.
- **Windows.** syft-job's arrival check failed on a Windows checkout in this test.
  The submitter declares a newline-normalized hash and the owner hashes raw bytes, so a
  CRLF file stays in the `received` state. The Flywheel verifier itself runs on
  Windows.
- **PyPI.** syft-job 0.1.40 on PyPI predates PR #9536 and its approved hash, so the
  `pysyft` extra waits for the next syft-job release. Flywheel's core and the verifier
  stand apart from syft; `harness/pysyft_adapter.py` works on a `JobClient` the caller
  already built.

## What the receipt covers

A passing check shows that the key holder issued this body, that the body binds the
approved job, the approval record PySyft wrote, the score and the per-item rows, and
that every digest recomputes. The score is consistent with the rows; the rows are
rescored once the hidden answers are revealed. The identity of the hidden model and
data rests on the enclave attestation link, and the choice of benchmark and scoring
rule rests on its own review.

Every receipt carries the same seven-line `scope` list, fixed in
`harness/job_result_receipt.py`, and the verifier rejects a receipt whose list
differs by a word. Records of the older version (`flywheel.pysyft-job-result/v1`)
name the list `does_not_prove` and carry the v1 wording (`SCOPE_V1`); the
verifier checks each version against its own list, and the embedded
`superstack.receipt/1` names its copy `does_not_prove` because that contract is
vendored. Print the current list with:

```bash
python -c "import harness.job_result_receipt as m; print(*m.SCOPE, sep='\n')"
```

One test shows the rows' limit outright: a signer who lies consistently
in the rows, and rebuilds every digest including `receipt_id`, passes every check until
the answers are revealed. A lie that leaves `receipt_id` stale fails before the reveal.

## Licences

PySyft is Apache-2.0, and Flywheel carries none of its code. `harness/pysyft_job_hash.py` restates
the hash format and names its source file and commit. The superstack contract file is
vendored under its own FSL-1.1-MIT notice.
