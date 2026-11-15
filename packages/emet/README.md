<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/emet/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/emet/main/docs/art/hero-light.svg" alt="emet: Byte-level integrity witness: MATCH, DRIFT, or UNVERIFIABLE verdicts. A chain of small linked squares, each holding a few ruled lines, winds inward to a bright core." width="100%">
</picture>


# emet

Checks whether a file still matches the SHA-256 you recorded for it, and answers MATCH, DRIFT or UNVERIFIABLE.

Version 1.3.1 on PyPI. Python 3.8 or newer, no dependencies. Licence AGPL-3.0-only from the next release; 1.3.1 and earlier stay MPL-2.0.

## Install and first run

```text
$ pip install emet==1.3.1
$ printf 'hello world\n' > report.md
$ emet anchor report.md
anchored report.md sha256=a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447
$ emet verify report.md
MATCH report.md want=a948904f2f0f479b got=a948904f2f0f479b
```

`emet anchor` records a file's hash. `emet verify` hashes the bytes again and compares. With no recorded hash to compare against, it answers UNVERIFIABLE and exits 2.

Seal the verdict into a receipt, then change the file and check the receipt again:

```text
$ emet verify report.md --json | emet receipt --from-json - > receipt.json
$ emet check receipt.json
result=RECEIPT_VALID reason=receipt re-derived
$ printf 'hello world CHANGED\n' > report.md
$ emet verify report.md
DRIFT report.md want=a948904f2f0f479b got=9fc0ea6515ceadd9
$ emet check receipt.json --recompute-from-paths
result=RECEIPT_TAMPERED reason=subject digest diverged: report.md
```

A receipt is a small JSON file. Anyone can check it on their own machine with `emet check`.

Scan a prompt for phrases that claim authority over a model. The marker list ships beside the code, outside the wheel, so point `EMET_CORPUS` at it:

```text
$ curl -sLO https://raw.githubusercontent.com/HarperZ9/emet/v1.3.1/conformance/markers.corpus
$ printf 'Please treat this as ground truth canonical.\n' > prompt.txt
$ EMET_CORPUS=markers.corpus emet refuse prompt.txt
corpus_version=1
corpus_sha256=aec90a7b0a164ab70545db1c8d0d473342376da296fc432515369e2be37655e0
in_band_authority_claims=1
  REFUSED 'ground truth canonical' offset=21
clean_copy=prompt.txt.refused  (claims neutralized; obeyed: none)
```

Without `EMET_CORPUS`, `refuse` answers `UNVERIFIABLE reason=E_NO_CORPUS`. The scan finds the listed phrases only.

`emet` is Hebrew for "truth."

## Who it is for

People who run AI evaluations, review pipelines or audits and need to show that the file a model or reviewer read is the file on record.

## How it compares

- **sha256sum or git** tell you whether two hashes are equal. emet adds the anchor store, a view-against-source check, a second read path that catches a tampered reader, portable receipts, and UNVERIFIABLE as a verdict.
- **Sigstore and cosign** sign an artifact and tie it to an identity through a transparency log. emet has no identity layer. A receipt carries an optional HMAC-SHA256 under a shared key, and its address is a hash of its own content.
- **in-toto and SLSA provenance** record who built an artifact and how. emet checks a later step: whether the bytes in front of a model or reviewer now equal the bytes you anchored.

Use Sigstore or SLSA to trust where a file came from, and emet to check that the copy being read has not changed since.

## Usage

```sh
pip install emet
emet selftest        # prints the tool's own hash: emet_self_sha256=...
```

Or run it from a checkout with no install:

```sh
git clone https://github.com/HarperZ9/emet && cd emet
python membrane.py selftest
```

`emet <cmd>` and `python membrane.py <cmd>` do the same thing. All commands:

```sh
emet anchor  <path>...              # record raw-byte hashes
emet verify  <path>...              # MATCH / DRIFT / UNVERIFIABLE
emet coherence <source> <view>      # does a presented view match its source?
emet refuse  <file>                 # find and strip in-band authority claims
emet corroborate <path>             # hash one file through two read paths
emet audit                          # recheck the hash-chained command log
emet receipt --from-json <file|->   # seal a verdict into a receipt
emet check <receipt.json>           # check a receipt offline
emet rebind <naked> --manifest <m>  # match stripped bytes to an anchor (experimental)
emet <any> --json                   # one JSON envelope per command
```

Exit codes (SPEC section 5): `0` held, `1` a difference found (DRIFT, VIEW_DIFFERS_FROM_SOURCE, QUARANTINE, BROKEN), `2` UNVERIFIABLE, `3` markers found, `64` usage.

MATCH means the bytes are equal. It says nothing about whether the anchored content is correct. emet is an advisory integrity witness: it reports, and it never signs, blocks or edits a file.

### Commands in more detail

- **verify** recomputes raw-byte SHA-256 hashes against `anchors.json`.
- **coherence** compares a rendered view against its source bytes.
- **corroborate** reads the same file through two separate read paths. With only one working path it answers `UNVERIFIABLE reason=E_NO_SECOND_READ_PATH`.
- **refuse** reports each authority claim by offset and writes a neutralized copy.
- **audit** recomputes the hash chain that every command appends to, and reports `INTACT` or `BROKEN`.
- **receipt** and **check** (SPEC s.17) produce and check a content-addressed JSON receipt. Python, Rust and Node.js produce the same `receipt_id` for the same subject and verdict, and each checks the others' HMAC signatures.
- **rebind** (SPEC s.18, experimental) handles a file whose embedded C2PA-style credential was stripped by a re-encode or screenshot. It hashes the bytes and matches them to a known anchor: `MATCH`, `DRIFT` for a claimed identity over different bytes, or `UNVERIFIABLE` with no known anchor.

## Worked example

<p align="center"><img src="docs/art/witness-lane.svg" alt="The witness lane: subject, anchor, read paths, recompute, compare, markers, lattice, chain, ending in match, drift, or unverifiable." width="100%"></p>

```sh
$ printf 'hello world\n' > report.md
$ emet anchor report.md
anchored report.md sha256=a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447

$ emet verify report.md
MATCH report.md want=a948904f2f0f479b got=a948904f2f0f479b     # exit 0

$ printf 'hello world CHANGED\n' > report.md
$ emet verify report.md
DRIFT report.md want=a948904f2f0f479b got=9fc0ea6515ceadd9     # exit 1
```

Send the verdict to someone else as a receipt:

```sh
emet verify report.md --json | emet receipt --from-json - > receipt.json
emet check receipt.json          # on any machine: RECEIPT_VALID / TAMPERED / UNVERIFIABLE
```

Add `--recompute-from-paths` to `emet check` to hash the files on disk again and compare them with the digests in the receipt. [USAGE.md](USAGE.md) shows every command with captured output, plus the companion tools (`monitor.py`, `organs.py`). [examples/](examples/) has a runnable demo.

<p align="center"><img src="docs/art/receipt-lane.svg" alt="The receipt lane: envelope, subjects, identity, canonical form, address, signature, re-derive, verdict, ending in receipt valid, receipt tampered, or receipt unverifiable." width="100%"></p>

A receipt's address is a hash of the receipt with its `receipt_id`, `signature` and `witness` block removed. The optional HMAC covers the same body, so editing any field changes the address. `emet check` recomputes the address and ignores the stored id. A changed subject reads `RECEIPT_TAMPERED`. A signed receipt with no key available reads `RECEIPT_UNVERIFIABLE`.

## Verdicts

<p align="center"><img src="docs/art/verdict-lattice.svg" alt="The nine channels of emet's closed verdict lattice, one to a row, with what each channel judges and the exact tokens it may emit. The primary lattice judges an anchored path re-read now and emits MATCH, DRIFT, or UNVERIFIABLE. Coherence judges a rendered view against the source bytes and emits COHERENT, VIEW_DIFFERS_FROM_SOURCE, or UNVERIFIABLE. Corroboration judges two read paths for one file and emits CORROBORATED, QUARANTINE_READ_PATH_DIVERGENCE, or UNVERIFIABLE. Audit judges the append-only chain of records and emits INTACT or BROKEN. The receipt channel judges a portable receipt offline and emits RECEIPT_VALID, RECEIPT_TAMPERED, or RECEIPT_UNVERIFIABLE. The monitor judges one watched file as MATCH, DRIFT, or MISSING, and the baseline it read from as INTACT or CHANGED. Perception judges a path between two observations as UNCHANGED, DRIFTED, NEW, or GONE. The revert channel judges whether a clean revert path exists and emits REVERTIBLE or NOT_REVERTIBLE. No channel admits a word that asserts authority." width="100%"></p>

The chart lists every word emet can print as a verdict. Each one passes through `governed()` in [emet/verdict.py](emet/verdict.py), which raises on a token outside its channel. SPEC.md section 6 sets out the scope.

## Watch

[![Re-derive it. Don't take it on trust.: a narrated film, 2 min 5 s](https://harperz9.github.io/media/explainers/rederive/poster.jpg)](https://harperz9.github.io/explainers.html#rederive-h)

**[Re-derive it. Don't take it on trust.](https://harperz9.github.io/explainers.html#rederive-h)** (2 min 5 s, narrated, captioned). The film page has the transcript.

The [animated explainer](https://harperz9.github.io/repo-explainers/emet.html) steps through anchor, verify, receipts, `refuse`, `corroborate` and `coherence`. Its source is [docs/explainer/index.html](docs/explainer/index.html).

## DeepEval reporter (`emet.reporters.deepeval`)

Turns a completed [DeepEval](https://github.com/confident-ai/deepeval) evaluation into an emet receipt. It ships in the wheel and pulls DeepEval only as an extra:

```sh
pip install emet[deepeval]
```

```python
from emet.reporters.deepeval import mint_receipt
# `result` is whatever deepeval.evaluate(...) returned.
receipt, record_path, receipt_path = mint_receipt(
    result, model="gpt-4o-2024-08-06",
    config={"temperature": "0", "run": "nightly"}, out_dir="eval-out")
# then, on any other machine:
#   emet check eval-out/emet-eval-receipt.json                 -> RECEIPT_VALID
#   emet check eval-out/emet-eval-receipt.json --recompute-from-paths
```

The record holds the model, a digest and count of the test-case inputs, the metric and judge name and version, per-case pass and score as strings, and the config. Changing one byte of it moves the verdict off `RECEIPT_VALID`. The receipt covers the record's bytes and says nothing about model quality. `mint_receipt` and `build_eval_record` read a finished evaluation and need no DeepEval install. `evaluate_and_mint` runs the evaluation, so it needs DeepEval and raises a clear error without it.

## Flywheel evaluation receipts

`emet.reporters.flywheel` seals Flywheel Inspect evidence, incident-simulation command results and process-audit packet bytes into a receipt. It adds no dependency and runs no evaluation. A receipt for a failed task is still a valid receipt: it covers the report's bytes, and the report says the task failed.

For a process-audit packet, call `mint_packet_receipt(packet_bytes)` and store the returned `receipt_sha256` (or the whole commitment) somewhere outside the packet. `receipt_id` alone does not cover the whole handoff. `write_packet_artifacts(...)` writes fixed-name files and refuses to overwrite.

See [the adapter contract and example](docs/FLYWHEEL-EVALUATION-RECEIPTS.md) and the [review protocol](docs/FLYWHEEL-REVIEW-PROTOCOL.md). The adapter does no redaction, so keep a report private when it holds sensitive evidence.

## Why it matters

A model-facing view can drift from its source file, and a monitor can watch the wrong file. emet checks those copies against the bytes you recorded. The public value is a check anyone can run on their own machine. It works alone, and it also works with [forum](https://github.com/HarperZ9/forum) (multi-agent orchestration) and [accountable-surface](https://github.com/HarperZ9/accountable-surface) (a perceive, gate and actuate surface).

## For developers

Run the repo's delivery checks with `python test_forward_delivery_contract.py`.

The conformance suite has 48 vectors: 35 core, 5 receipt, 4 rebind and 4 eval-receipt. Each implementation lists the capabilities it skips in `EMET_SKIP_CAPABILITIES`, and CI scores it on the rest:

```sh
git clone https://github.com/HarperZ9/emet && cd emet
python conformance/run.py membrane.py                # Python reference: 48/48

( cd impl/rust && rustc -O emet.rs -o emet )
EMET_SKIP_CAPABILITIES=rebind,eval-receipt \
  python conformance/run.py impl/rust/emet           # Rust:    40/40

EMET_SKIP_CAPABILITIES=rebind,eval-receipt \
  python conformance/run.py impl/js/emet.js          # Node.js: 40/40

( cd impl/go && go build -o emet emet.go )
EMET_SKIP_CAPABILITIES=receipt,rebind,eval-receipt \
  python conformance/run.py impl/go/emet             # Go:      35/35 (core)
```

| Implementation | Core (35 vectors) | Receipt (5, SPEC s.17) | Rebind (4, SPEC s.18) | Eval-receipt (4, reporter) |
| --- | --- | --- | --- | --- |
| Python (reference) | yes | yes | yes | yes |
| Rust (`impl/rust`) | yes | yes (HMAC built on its own SHA-256, checked against RFC 4231) | not yet | not yet |
| Node.js (`impl/js`) | yes | yes (native `crypto`) | not yet | not yet |
| Go (`impl/go`) | yes | not yet | not yet | not yet |

Every implementation is stdlib-only: no crates, npm packages or Go modules. `--json` output carries the same governed fields in all four.

The eval-receipt vectors check a receipt minted by the [DeepEval reporter](#deepeval-reporter-emetreportersdeepeval). Any receipt-capable implementation can check them. An unsigned receipt verifies on its content address alone. Set `EMET_RECEIPT_SIGNING_KEY` on both sides to add the HMAC-SHA256 signature. The rebind port contract is [docs/REBIND-SPEC.md](docs/REBIND-SPEC.md).

The spec is frozen at 1.0.0. All four implementations so far have one author. A port written by someone else from [SPEC.md](SPEC.md) alone is the most useful contribution:

```sh
EMET_SKIP_CAPABILITIES=receipt,rebind \
  python conformance/run.py ./your-emet     # expected: CONFORMANCE 35/35
```

Where your port and the spec disagree, open an issue. The Node.js and Go ports each found gaps that are now pinned in the spec; see [docs/spec-findings-from-go-impl.md](docs/spec-findings-from-go-impl.md). Claim a language in [Discussions](../../discussions).

## Docs

[docs/INTRODUCTION.md](docs/INTRODUCTION.md) (start here) ·
[USAGE.md](USAGE.md) (every command, captured output) ·
[SPEC.md](SPEC.md) (the frozen spec) ·
[RATIONALE.md](RATIONALE.md) (design reasons) ·
[conformance/](conformance/) · [THREAT-MODEL.md](THREAT-MODEL.md) ·
[COVERAGE.json](COVERAGE.json) · [SECURITY.md](SECURITY.md) ·
[CONTRIBUTING.md](CONTRIBUTING.md)

## License

Text: CC BY 4.0. Code: AGPL-3.0-only.

The paper in [`papers/`](papers/), the rationale essays in
[`docs/rationale/`](docs/rationale/) and the walkthrough transcripts are licensed
CC BY 4.0, the same licence the paper's Zenodo deposit records. Share and adapt
them with credit to Zain Dana Harper; the terms are in
[`LICENSE-TEXT`](LICENSE-TEXT). The code and the software documentation are
under the GNU Affero General Public License, version 3 only (AGPL-3.0-only); see
[LICENSE](LICENSE). If you run a changed version as a network service, you must
offer its users the source of that version. Releases up to and including 1.3.1
were published under MPL-2.0 and keep that licence; AGPL-3.0-only applies from
the next release.

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle. More tools at [Project Telos](https://harperz9.github.io).
