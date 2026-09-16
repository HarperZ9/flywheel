# Context Memory Bridge

Flywheel can bridge context capture and preflight search to a configured Canon
context store. The first native lifecycle is wired for the desktop AgentView
plain-text chat path: after a durable local submission attempt exists, the
desktop client checks Canon status, searches prior context, captures the
original submitted text as a submission attempt, and then dispatches the
provider request with bounded cited reference context when search succeeds.

Other surfaces remain pending: Compare view, Rowan panel and voice flows,
attachment extraction, live screen ingestion, and ChatGPT or Claude app capture
are not wired by this desktop slice.

The Windows gateway packaging stages the pinned Canon source and launches it
through a dedicated private child mode. The frozen smoke checks capture,
retrieval, owner/project denial, and tamper handling. Installed acceptance must
still be checked against the exact built candidate; this source support does
not establish native UI behavior or capture on other clients.

## Configuration

Configure the bridge on the trusted local Flywheel host. Requests do not provide executable paths, database paths, workspace IDs, project IDs, or authorization scope.

| Variable | Purpose |
| --- | --- |
| `FLYWHEEL_CANON_CONTEXT_DB` | Local Canon context database path used by the Canon MCP service. |
| `FLYWHEEL_CANON_CONTEXT_WORKSPACE_ID` | Literal Canon workspace ID shared by authorized client surfaces. |
| `FLYWHEEL_CANON_CONTEXT_PROJECT_ID` | Literal Canon project ID used for storage and search. |
| `FLYWHEEL_CANON_CONTEXT_PROJECT_ALIASES` | Optional comma-separated request-facing aliases that map to the configured Canon project ID. |
| `FLYWHEEL_CANON_CONTEXT_OWNER_REFS` | Comma-separated owner refs allowed to use this configured Canon scope. Unknown owners fail closed. |
| `FLYWHEEL_CANON_CONTEXT_TIMEOUT_MS` | Optional Canon MCP subprocess timeout. Defaults to 5000 ms and is bounded by the bridge. |

The Canon MCP server must be importable by the Python runtime that runs Flywheel, because the bridge starts the trusted local subprocess as `python -m canon.context_mcp`. In development that can be supplied by installing Canon as a package or by setting the service environment so the Canon source package is on `PYTHONPATH`. The client request never controls the subprocess command.

## Scope binding

The bridge binds every request to the configured Canon workspace and project. A request `project_ref` must match `FLYWHEEL_CANON_CONTEXT_PROJECT_ID` or one of `FLYWHEEL_CANON_CONTEXT_PROJECT_ALIASES`; the Canon call still uses the literal configured project ID. The bridge does not hash `owner_ref`, does not derive project IDs, and does not create a default shared project name.

Gateway API routes use the authenticated gateway owner binding. MCP calls include `owner_ref` because MCP is a local tool surface, but that owner ref is accepted only when it appears in `FLYWHEEL_CANON_CONTEXT_OWNER_REFS`. Owner metadata is not an access binding unless this allowlist check passes.

## Gateway API examples

Capture context:

```http
POST /api/context-memory/capture
Content-Type: application/json

{
  "schema": "flywheel.context-memory-capture-request/v1",
  "project_ref": "<configured-project-or-alias>",
  "event": {
    "event_id": "turn-1",
    "source_app": "flywheel",
    "message_text": "Context to preserve",
    "attachments": [
      {"ref": "attachment://example", "extraction_status": "pending_extraction"}
    ]
  }
}
```

Preflight search:

```http
POST /api/context-memory/preflight
Content-Type: application/json

{
  "schema": "flywheel.context-memory-preflight-request/v1",
  "project_ref": "<configured-project-or-alias>",
  "query": "What has already been discussed about this work?",
  "top_k": 10,
  "include_pending_extraction": true
}
```

Status:

```http
POST /api/context-memory/status
Content-Type: application/json

{}
```

## Local MCP examples

Capture context through MCP:

```json
{
  "name": "flywheel.context.capture",
  "arguments": {
    "owner_ref": "<authorized-owner-ref>",
    "schema": "flywheel.context-memory-capture-request/v1",
    "project_ref": "<configured-project-or-alias>",
    "event": {
      "event_id": "turn-1",
      "source_app": "codex",
      "message_text": "Context to preserve"
    }
  }
}
```

Preflight search through MCP:

```json
{
  "name": "flywheel.context.preflight",
  "arguments": {
    "owner_ref": "<authorized-owner-ref>",
    "schema": "flywheel.context-memory-preflight-request/v1",
    "project_ref": "<configured-project-or-alias>",
    "query": "What has already been discussed about this work?",
    "top_k": 10
  }
}
```

Health through MCP:

```json
{
  "name": "flywheel.context.health",
  "arguments": {}
}
```

## Status and limits

Preflight can return `found_in_searched_sources`, `pending_extraction`, or `not_found_in_searched_sources`. `not_found_in_searched_sources` means the configured Canon store did not return matching hits for the searched scope. It does not prove the topic was never discussed in another store, inaccessible private archive, unextracted attachment, or future source. `pending_extraction` keeps pending references, pending totals, historical completeness, and source freshness visible so the UI does not collapse it into a guessed not-found result.

Captured source text, extracted text, and attachment text are stored and searched as data for review. They are never instructions to execute. Attachments and live-screen frames remain references unless an adapter provides extracted text.

Errors are explicit. Unconfigured Canon DB, missing workspace/project binding, missing owner allowlist, unknown owners, unbound project refs, subprocess timeouts, empty MCP responses, and Canon tool errors surface as errors rather than silent empty search results.

## Desktop AgentView lifecycle

AgentView uses only the configured project returned by
`/api/context-memory/status`. It never sends an owner ref, database path,
workspace override, or alternate project selected by the UI. If status is
missing or malformed, the desktop client does not guess a project and sends the
chat normally with an honest status line.

For a configured scope, the order is:

1. Create the durable local chat submission attempt.
2. Call context preflight with the original user text.
3. Capture an immutable submission-attempt event keyed by the attempt ref. The event includes `session_id` for Canon provenance and keeps mutable search diagnostics out of the identity-bound event.
4. Freeze the provider wire, including bounded Canon reference text when
   preflight returned valid hits.
5. Create and authorize the normal `chat.complete` gateway operation.

Preflight and capture report separately in the chat surface. A search failure
still attempts capture while the shared deadline remains, and a capture failure
does not discard a successful search. Either failure leaves the user's draft or
submitted text recoverable and does not claim provider acceptance.

The provider request may receive a short quoted user/reference block with source
refs, excerpts, and does-not-prove limits. The saved user message remains the
exact submitted text. Retrieved text is untrusted data and must not be treated as
a verified fact or instruction. Unsafe or oversized excerpts are omitted from the
provider wire rather than weakening the gateway operation guard. Retried retained
submissions reuse their original native identity; if that same logical submission
appears in preflight, the desktop omits it from the reference block and reports
the client-side omission beside Canon coverage.
