# Claude Code account auth completion

Flywheel treats Claude Code account auth as owned by the official Claude Code
CLI. The app never asks for `claude setup-token` output, never stores a Claude
Code OAuth token, and never treats a binary name by itself as account proof.

The Anthropic subscription row now follows this contract:

- Status probes run `claude auth status --json` through the resolved native
  executable. A row is authenticated only when the JSON is typed as
  `loggedIn: true`, `authMethod: "claude.ai"`, and
  `apiProvider: "firstParty"`.
- Exit 1 with typed `loggedIn: false` is reported as not signed in. Exit 0 with
  logged-out data, malformed JSON, wrong types, or unrecognized auth/provider
  strings is unknown, not authenticated.
- Account metadata and machine details stay out of public responses. The code
  drops email, org fields, projects directory, raw stdout/stderr, full path, and
  private executable identity.
- Sign-in starts only after a human clicks the UI path. The engine resolves the
  native executable, rejects `.warden/bin` wrappers for auth operations, rechecks
  executable identity, and then launches `claude auth login` without capturing
  stdout or stderr.
- Direct Anthropic API key use remains the separate `anthropic` endpoint/key
  path. It does not make `claude-cli` a subscription account row.

Desktop behavior:

- The model picker ranks `claude-cli` above keyed providers only when
  `account_authenticated` is true.
- A present-but-unauthenticated Claude CLI stays visible as `sign-in needed` and
  is not selectable for a first send.
- The sign-in panel opens native Claude Code account sign-in and offers refresh
  after return. It does not render a token paste field for Anthropic.

Focused review receipts used for this change:

```powershell
$env:TEMP='D:/t'; $env:TMP='D:/t'
python -m pytest tests/test_claude_cli_auth.py tests/test_auth_presence_labels.py `
  tests/test_endpoint_registry.py tests/test_oauth_completion.py `
  tests/test_oauth_service.py tests/test_oauth_lifecycle.py `
  tests/test_claude_model_selection.py -q --basetemp D:/t/fw-claude-auth-pytest
```
