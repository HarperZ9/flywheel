# Context Memory Backend Bridge

Flywheel can bridge context capture and preflight search to a configured Canon context store. This is a backend bridge only. Automatic chat lifecycle insertion, desktop UI, and full native review flows are not wired in this pass.

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

Preflight can return `found_in_searched_sources` or `not_found_in_searched_sources`. `not_found_in_searched_sources` means the configured Canon store did not return matching hits for the searched scope. It does not prove the topic was never discussed in another store, inaccessible private archive, unextracted attachment, or future source.

Captured source text, extracted text, and attachment text are stored and searched as data for review. They are never instructions to execute. Attachments and live-screen frames remain references unless an adapter provides extracted text.

Errors are explicit. Unconfigured Canon DB, missing workspace/project binding, missing owner allowlist, unknown owners, unbound project refs, subprocess timeouts, empty MCP responses, and Canon tool errors surface as errors rather than silent empty search results.