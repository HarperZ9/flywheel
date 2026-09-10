# Native agent history reads

`GET /api/agent/runs` and `GET /api/agent/run` require the configured gateway
bearer token and an allowed Host. These private routes return `AUTH_REQUIRED`
with HTTP 401 when authentication is disabled or absent. Other public routes
retain their existing auth-off behavior.

The detail request accepts exactly one `id` parameter containing 16 hexadecimal
characters. Uppercase is accepted and normalized to lowercase. Whitespace,
path syntax, duplicate parameters and additional parameters are rejected.
Successful detail responses retain the stored run fields and computed `intact`
flag. This flag establishes consistency with the stored document identifier;
it does not establish factual accuracy or independently authenticate execution.

The list request accepts an optional `limit` from 1 through 100, default 20.
It examines at most 1,000 directory entries and reports `scan_limited: true`
when that bound is reached. A limited scan is not a complete history inventory.
Selected entries remain ordered by modification time within the scanned set.
Only opaque run filenames are considered. Unreadable selected entries retain
an `UNREADABLE` row with `intact: false` and no file content.

Both readers use the existing private-artifact filesystem capability. Reads
reject reparse/symlink paths, nonregular files and unsafe root replacement;
unsupported storage has no ordinary-path fallback. Each document is limited
to 1 MiB and 32 JSON nesting levels. Duplicate JSON keys and nonfinite numbers
are rejected. The writer and original content-address calculation are unchanged.
Legacy files beyond these read bounds remain stored but cannot be opened by
these endpoints.

Errors use the existing `flywheel.evidence-transport-error/v1` envelope with
an `error.code` and fixed message. Rejected IDs, filesystem paths and raw
exceptions are not included.

| HTTP status | Code | Meaning |
|---|---|---|
| 400 | INVALID_REQUEST | Invalid identifier, query or limit |
| 401 | AUTH_REQUIRED | Private gateway authentication is required |
| 403 | UNSAFE_PATH | Storage path cannot be read safely |
| 404 | NOT_FOUND | No stored run with this identifier |
| 413 | TOO_LARGE | Stored document exceeds the read bound |
| 422 | UNREADABLE | Stored content is not a supported JSON object |
| 503 | UNAVAILABLE | Storage cannot currently be read |

This repair adds no new ledger-content exposure, persistence, export or
retention policy. Existing tool-output truncation and missing-ledger states
remain separate from access control. Synthetic HTTP and filesystem regressions
exercise the private-route boundary without reading operator history.
