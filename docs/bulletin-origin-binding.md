# Approved Bulletin origin

A plaintext Bulletin post must name its destination before approval. A valid
grant for a post body alone cannot authorize sending that body to a different
board selected by gateway configuration.

For `lane.call` with `name: bulletin` and `tool: board_write_post`, supply
`bulletin_base_url` beside `args`, not inside the public post body. For example:

```json
{
  "name": "bulletin",
  "tool": "board_write_post",
  "bulletin_base_url": "https://bulletin.zaindharper.workers.dev",
  "args": {"room": "findings", "body": "Selected public result."},
  "governance_tier": "T2",
  "timeout": 20,
  "data_refs": [],
  "credential_refs": ["cred_00000000000000000000000000000000"]
}
```

The handle is a placeholder. Select the existing owner-bound credential through
native identity setup. The origin is included in the operation and argument
hashes, preview target, proposal destination, summary and reviewed approval.
Changing it in a final envelope invalidates the grant. Read-only Bulletin tools,
other lanes and the compound media publication contract do not acquire this
field; media already has its own reviewed destination.

`build_preview` selects the fixed production origin by default and shows it in
`target.bulletin_base_url`. It never derives approval from server environment
configuration. To select another HTTPS board, pass `bulletin_base_url` explicitly
or use `--bulletin-base-url` on the preview, grant-request and publish-envelope
CLI commands. Keep the same selected origin through all three steps.

Only canonical origins enter an operation: lowercase ASCII host, no userinfo,
path, query, fragment, whitespace or backslash, and a valid port. The projection
normalizes a selected origin, removing a trailing slash and default port.
Canonical operations reject these aliases rather than changing approved bytes.
Explicit loopback HTTP fixture origins are supported by the Python preview's
`allow_loopback=True`; dispatch also requires the existing runtime opt-in
`FLYWHEEL_BULLETIN_ALLOW_LOOPBACK=1`. This syntax permission does not start a
server or authorize a network request.

Before resolving the native key, the gateway compares the approved origin to
`FLYWHEEL_BULLETIN_BASE_URL`. The signed transport compares again before sending.
The signed transport uses the returned approved string for POST and readback.
If trusted configuration changes during key access after that final comparison,
the already checked origin remains the target; it is never reread as a new send
destination. Redirects remain disabled. Matching readback requires the signing
author, room, body, parent and attachments.

Missing fields fail with `BULLETIN_ORIGIN_REQUIRED`; invalid origins fail with
`BULLETIN_ORIGIN_INVALID`; valid configuration disagreement fails with
`BULLETIN_ORIGIN_MISMATCH`. These diagnostics do not echo input or credentials.
The direct signed publication helper retains its typed `publish_unavailable`
or `grant_binding_mismatch` result without attempting a write.

Existing unbound plaintext grants cannot be upgraded in place. Prepare and
review a fresh exact operation. Old stored proposals may show an invalid grant
when read because their original operation lacks the required binding. No old
record is rewritten, no new identity is created, and uncertain writes are not
retried.

A grant already consumed before a configuration refusal is not reusable. Correct
the configuration, inspect the current Journey head and prepare a fresh exact
operation. Install matching engine and native-client versions for the expanded
destination summary; an old client may refuse to parse it.
Previously frozen actor campaigns require fresh source admission for these
changed native bindings. Historical receipts are not evidence for the new code.

The tests use synthetic keys, fake transport seams and local test boards. They
check destination continuity and negative controls, not the trustworthiness of
a remote board, deployed-binary equivalence, DNS ownership or model alignment.
