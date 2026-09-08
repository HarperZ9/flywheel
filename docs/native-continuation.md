# Native continuation preview

Flywheel can start a new Evidence Journey from a local workspace root and an optional local export without claiming provider-native web session resume. The route is for recovery and continuation health: it shows the repo state, mapped import rows, selected export signals, and omissions before another agent turn is started.

## Flow

1. `POST /api/continuation/preview` with a workspace root and optional local export path.
2. The gateway resolves the workspace root, reads current git state, runs the existing import adapter, scans the selected export in a bounded byte window, and stores two records:
   - a private preview record that may contain local paths for the native UI;
   - a public-safe intake artifact that carries only projection metadata: hashes, repo state, import mapping summaries, selected relative file pointers, counts, omission rows, a private context ref, and does-not-prove limits.
3. `POST /api/continuation/context` with the preview ref, preview hash, and source-state hash to retrieve the source-bound private context package and runner context for the existing Flywheel agent loop. This route is local/private and is rechecked for source drift before returning context.
4. `POST /api/continuation/start` with the preview ref, preview hash, source-state hash, and client request id.
5. The route recomputes the source state. If the workspace or export changed, it returns `SOURCE_DRIFT` and creates no Journey. If required source state is missing, it returns `CONTINUATION_BLOCKED` before grant preparation. If the state still matches and the preview is ready, it prepares and approves a fresh exact Journey create grant, calls the existing Journey route, then appends a source-bound Rescue next-action pointing at the private context route.
6. The native client opens the resulting Journey with the Rescue lens and shows private context counts plus selected relative files in the preview card.

`POST /api/continuation/undo` appends a bounded rollback next-action to the Journey through the same grant and Journey append path. It does not delete or rewrite the source workspace, preview, or Journey history.

## Boundaries

The intake artifact intentionally omits provider grants, jobs, schedules, credentials, raw host paths, selected task text, selected summary text, and bulk transcript text. The private preview keeps the selected task context local and excludes credential-shaped values with explicit `CREDENTIAL_EXCLUDED` omissions when those values are encountered. Oversized exports are read only through the bounded prefix; the route records a prefix hash and file metadata rather than a full-file SHA-256 for truncated exports.

This does not prove that a future model loaded the context, that attachments were available, that an undo restored files, or that a provider-native session can be resumed. Unsupported provider-native resume remains visible until a connector proves read, list, resume, and fork semantics.

Credential exclusion runs before signal and attachment parsing over the bounded
export text. It recognizes common prefixed environment assignments, OAuth token
and client-secret assignments, bearer values, and private-key blocks. Multi-line
quoted values and unclosed private-key blocks remain excluded through their end
or the preview boundary. Source line numbers and original line hashes are retained;
task text outside recognized spans remains available. A credential block cannot
supply an attachment path or a new user-direction signal.

Pattern detection is incomplete for unknown or encoded secret formats. This is
not a credential-transfer mechanism: use the existing keychain and supported
provider sign-in routes for credentials. Native OAuth portability and arbitrary
provider-native session resume are separate capabilities, not implied by import.
