# Review Inspect evidence in Flywheel

The Receipts view can import an Inspect JSON log and reopen its saved report.
The report keeps source locations and reported scores available for review.
Importing a log does not validate the scorer, certify the evaluation, or grant
permission for another action.

## Desktop workflow

1. Open Receipts and select **Select Inspect JSON**. Use a version 2 JSON export;
   native `.eval` archives require conversion through Inspect first.
2. Inspect the selected file's digest and byte length, then choose
   **Request approval**. The existing Journey approval flow binds the operation
   to those exact bytes. Selecting a different file requires a new approval.
3. Review the reported status together with assessment, invalidation, coverage
   and semantic verification. A run can report `success` while its assessment
   is `incomplete`, or while individual answers are incorrect.
4. Expand a source row to inspect its JSON pointer and full selected value.
   The pointer addresses the imported JSON, not the original `.eval` archive.
5. Reopen saved reports from recent Inspect imports. This list shows the newest
   ten imports; the API provides pagination for older records.

Cancellation in the file picker does not upload anything. Denying approval
prevents the import. The current proposal `reject` endpoint applies before
approval; it does not withdraw an approval already issued. Changing the scope
or uploaded bytes after approval is rejected at dispatch. Approval expiry and
Journey binding still apply.

## What is retained

The gateway stores the selected report and its source identity under the
configured Flywheel instance and owner. It retains the report across gateway
and desktop restarts. It does not retain the raw uploaded JSON.

Keep the source log if another reviewer needs to recompute its hash or inspect
fields outside the selected report. Selected fields can still contain sensitive
information; this importer is not a general redaction tool. Nothing in the
import workflow publishes a report to Bulletin or sends it to another service.

Readback checks the report's source binding, the stored entity hash, and the
local audit binding. These checks detect inconsistency against that stored
history. They do not authenticate the original producer or protect against a
complete coordinated rewrite of the records and local audit history.

## API contract

All routes use the existing gateway authentication. Upload also requires an
approved `import.inspect` operation for the current Journey and exact source.

`POST /api/import/inspect` accepts raw JSON bytes, at most 16 MiB. The native
gateway request uses `application/json` so it passes the shared gateway auth
gate; the route-level parser also recognizes
`application/vnd.flywheel.inspect-json` for direct/internal route validation.
The upload uses these headers:

| Header | Meaning |
| --- | --- |
| `Content-Length` | Actual upload byte length |
| `X-Flywheel-Inspect-Byte-Length` | Length bound into approval |
| `X-Flywheel-Inspect-Sha256` | Full SHA-256 bound into approval |
| `X-Flywheel-Inspect-Filename` | Optional sanitized basename; no client path |
| `X-Flywheel-Journey-Ref` | Journey reference |
| `X-Flywheel-Expected-Event-Head` | Approved Journey event head |
| `X-Flywheel-Client-Request-Id` | Request identity from the proposal |
| `X-Flywheel-Grant-Ref` | Issued operation grant |

The `flywheel.inspect-import-result/v1` response contains `source`, `data_ref`,
`report`, and `stored`. The nested report uses
`flywheel.inspect-evidence/v1`. Its `source_pointers` entries carry
`json_pointer` and `source_value`; sample score entries carry `scorer` and
`value`.

`GET /api/import/inspect?limit=20&offset=0` returns
`flywheel.inspect-import-list/v1` with bounded metadata in `items`. The limit
is capped at 50. It does not return full reports in the list.

`GET /api/import/inspect/<eid>` returns the saved import-result wrapper for
that instance and owner. Missing records return `NOT_FOUND`; inconsistent
stored evidence returns `STORE_TAMPERED`. A source mismatch during upload or
between importer output and upload is a failure, never an accepted report.

## Check the workflow

The loopback acceptance tests use the actual gateway, bearer authentication,
HTTP approval routes, the genuine importer, and versioned projected Inspect
fixtures. They exercise restart/readback, changed input, denied approval and
store tampering without contacting a model provider:

```text
python -m pytest tests/test_inspect_evidence_http.py -q
```

The desktop tests cover file selection, approval, report parsing, source
context, invalidation and saved-report reopening. Full desktop checks are:

```text
flutter analyze
flutter test
```

Run those commands inside `desktop/`. Widget tests and loopback tests do not
establish installed Windows or Android device acceptance. See
[Inspect evidence](INSPECT-EVIDENCE.md) for producer compatibility and
[METR interoperability](METR-INTEROP.md) for the separate task-execution
boundary.
