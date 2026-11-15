# Flywheel evaluation receipts

`emet.reporters.flywheel` is an optional adapter for exact Flywheel JSON report
bytes. It does not import Flywheel, run Inspect, execute an incident simulation,
call a scorer, or access the network. Its core minting APIs return bytes to the
caller; the packet helper `write_packet_artifacts(...)` is the only filesystem
writer and writes only fixed-name artifacts into a caller-selected directory.

The adapter accepts UTF-8 JSON bytes for three supported schemas:

- `flywheel.inspect-evidence/v1`
- `flywheel.incident-sim-command/v1`
- `flywheel.incident-sim-process-audit/v1` through the packet-specific API

Each input carries a list of what it covers. Newer Flywheel output names that
list `scope`; older output names it `does_not_prove`. The adapter reads either
name. Its own records name their list `scope` and say what each record covers:
the evaluation record and the packet record (schema version 2) cover the hash
and length of the exact bytes and the producer fields copied from them; the
packet commitment (version 2) covers the packet, record and receipt hashes.
Version 1 records named the same list `does_not_prove`.

It returns a portable EMET witness receipt plus two fixed-name byte artifacts for
the caller to persist:

```python
from emet.reporters.flywheel import build_eval_record, mint_receipt

record = build_eval_record(raw_flywheel_json_bytes)
receipt, artifacts = mint_receipt(raw_flywheel_json_bytes)

artifacts["flywheel-evaluation.json"]  # exact raw bytes supplied by caller
artifacts["flywheel-record.json"]      # canonical EMET metadata record bytes
```

For a final incident-sim process-audit packet, use the packet API so the caller
also receives the whole-receipt hash that a reviewer must retain separately:

```python
from emet.reporters.flywheel import mint_packet_receipt, write_packet_artifacts

receipt, artifacts, commitment = mint_packet_receipt(packet_json_bytes)
written_paths = write_packet_artifacts("packet-review", receipt, artifacts, commitment)

commitment["packet_sha256"]    # exact packet bytes
commitment["receipt_sha256"]   # required whole-receipt hash, including witness block
commitment["receipt_id"]       # supplementary EMET content address
```

`write_packet_artifacts` validates the exact artifact key set before creating
the output directory, creates only fixed-name files, and refuses to overwrite
existing outputs, including dangling links. If another process creates an output
after preflight, exclusive creation fails closed. Any already reserved files may
remain for inspection; the helper does not perform cleanup that could delete
caller-owned evidence. The helper is storage convenience, not independent
retention. The reviewer still needs to retain `receipt_sha256` or the full
commitment bytes that contain it somewhere outside the packet-local digest graph.
`receipt_id` is useful supplementary context, but it does not bind the whole
handoff.

The receipt is minted from an anchor-style command envelope. It addresses both
artifacts by SHA-256 and keeps `verdict_record` empty. A valid receipt means the
receipt body re-derives, and, when checked with subject recomputation, the
persisted artifact bytes still match the recorded digests. It does not mean the
Flywheel report is semantically correct.

For packet receipts, this also does not mean EMET stores the commitment
independently. The returned commitment object exists so a reviewer can preserve
the packet hash and whole-receipt SHA-256 separately. `receipt_id` is
supplementary context. A newly minted receipt over rewritten packet bytes can be
internally valid; comparing against the separately retained commitment is what
catches that substitution.

The metadata record copies only a bounded projection of producer claims after
checking closed tokens for the direct fields it projects:

- for Inspect evidence, `reported_status` must be one of `started`, `success`,
  `cancelled`, or `error`; `assessment` must be one of `reported`,
  `incomplete`, or `error`; `semantic_verification` must be `UNVERIFIABLE`;
  and `invalidated` must be boolean
- for incident simulation, the reported overall evaluation verdict must be one
  of `MATCH`, `DRIFT`, or `UNVERIFIABLE`

The record also stores the raw byte length and raw SHA-256. It labels semantic
conclusions as unverified by EMET. Private operator inputs, source values, local
paths, and trace contents remain in the raw Flywheel artifact only. This adapter
is not a general redactor; callers should store and share the raw artifact only
where its contents are allowed.

Malformed inputs fail before receipt construction with bounded `E_*` errors.
The parser rejects non-bytes input, oversized input above 16 MiB, invalid UTF-8,
duplicate JSON object keys, non-finite JSON numbers, non-string or unknown
schema values, excessive nesting, missing direct fields needed for the bounded
projection, wrongly typed direct fields, and unknown projected producer tokens.
It does not fully validate every nested Flywheel schema field.

One useful false-success control is an incident report whose Flywheel result says
`DRIFT`. EMET can still produce a valid integrity receipt for that report. The
receipt proves the report bytes were witnessed; it does not upgrade the reported
task result to a pass, prove the actions actually happened, or provide
independent ground truth.


Additional packet-specific false-success controls:

- a rebuilt process-audit packet can pass Flywheel packet-local integrity checks
  while the retained old EMET receipt reports `RECEIPT_TAMPERED`;
- a reminted receipt over the rebuilt packet can report `RECEIPT_VALID`, so the
  reviewer must compare the whole-receipt SHA-256 against the retained
  commitment; `receipt_id` can be checked as supplementary context;
- substituting the unaddressed EMET witness block can leave `receipt_id` valid,
  so retain the whole-receipt SHA-256 to detect changed declared witness
  metadata. This hash does not authenticate producer identity;
- a missing packet subject is `RECEIPT_UNVERIFIABLE` under subject recomputation.

Run the focused behavior proof:

```powershell
python test_reporter_flywheel.py
python -m pytest test_reporter_flywheel.py -q
```

The first command is the CI-compatible plain-script path. The second is a local
developer convenience when pytest is installed.
