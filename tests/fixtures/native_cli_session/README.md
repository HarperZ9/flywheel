# Native CLI review fixtures

Claude fixtures describe the current candidate profile. Codex fixtures retain
the earlier draft review shape for parser compatibility only. Codex native
prepare and launch return `AGENT_CLI_PROFILE_UNSUPPORTED`; these old bindings
fail execution validation. They must not be presented as a readiness receipt.

All paths and filesystem identities are synthetic. Fixtures contain no account
material and are derived from the backend binding/review functions.
