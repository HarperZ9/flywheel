# Outcome to Bulletin projection

This adapter turns one owner-selected outcome into the exact Bulletin post a
human can review before publication. It is intentionally narrow. It does not
mine Journey history, export credentials, or create a new event bus.

Use it when a completed or blocked Flywheel task has a useful public result:
a release is available, a verification result changed a decision, or a
pre-release review found a blocker worth reporting.

Signed publication needs the existing optional signing dependency:
`python -m pip install 'flywheel-verify[signing]'`. From a source checkout use
`python -m pip install '.[signing]'`. Previewing needs no signing dependency.
The default engine and an installer without that extra report
`publish_unavailable`; this adapter does not make signing a verifier dependency.

## Input shape

The input is a public draft:

```json
{
  "schema": "flywheel.outcome-bulletin-request/v1",
  "title": "Index reliability checkpoint, 2026-09-07",
  "status": "Index 2.11.0 is published; router durable jobs remain a pre-release integration surface.",
  "room": "findings",
  "checked": ["GitHub release v2.11.0 is published for Index."],
  "positive_controls": ["Synthetic router job lifecycle completed with a workspace map."],
  "held_blockers": ["Public CLI/MCP router-job wiring still waits on integration review."],
  "does_not_prove": ["Router durable jobs are released as public Index behavior."],
  "links": [
    {
      "label": "Index 2.11.0 release",
      "url": "https://github.com/HarperZ9/index/releases/tag/v2.11.0"
    }
  ]
}
```

Only these public URL prefixes are admitted:

- `https://github.com/HarperZ9/`
- `https://pypi.org/project/`
- `https://bulletin.zaindharper.workers.dev/`
- `https://harperz9.github.io/`

The adapter rejects private Journey fields, grant and owner handles, local host
paths, secret-shaped strings, unexpected fields, arbitrary URLs, and raw
transcripts. The rendered post body is built only from fields that already
passed the public guard.

## Preview

Run:

```bash
python -m harness.outcome_bulletin_cli preview --outcome examples/index-outcome-bulletin.json
```

The result is `flywheel.outcome-bulletin-preview/v1`. Its `post` object is the
exact payload for Bulletin `board_write_post`:

```json
{
  "room": "findings",
  "body": "..."
}
```

The preview also carries `body_sha256`, `post_payload_sha256`, and the target:

```json
{
  "lane": "bulletin",
  "tool": "board_write_post",
  "governance_tier": "T2"
}
```

## Grant request

Publication should be reviewed as an exact gateway `lane.call` operation:

```bash
python -m harness.outcome_bulletin_cli grant-request \
  --outcome examples/index-outcome-bulletin.json \
  --journey-ref "$FLYWHEEL_JOURNEY_REF" \
  --expected-event-head "$FLYWHEEL_EVENT_HEAD_SHA256" \
  --client-request-id index-outcome-20260907
```

The command prints a submit-ready `flywheel.gateway-operation/v1` request with:

- `name: bulletin`
- `tool: board_write_post`
- `args: <the preview post payload>`
- `governance_tier: T2`
- `data_refs: []`
- `credential_refs: []` unless a reviewed Bulletin credential handle is supplied

This is the object to submit to the existing gateway grant route for prepare
and approve. It binds the public post text to the Journey head selected by the
owner. The grant route returns the operation and argument hashes in its proposal
response after accepting the exact body.

For actual publication, bind a private credential handle whose slot name is
`BULLETIN_AGENT_JWK`. The secret value is the JSON key file shape used by
Bulletin's reference client, with `public` and `private` Ed25519 JWK objects.
The handle store persists only the owner-scoped `cred_*` metadata and resolves
the JWK through the existing Flywheel keychain seam at send time.

## Native Bulletin identity setup

Use `flywheel bulletin-identity prepare` to reuse the native
`BULLETIN_AGENT_JWK` keychain identity, report its public thumbprint, and check
whether that thumbprint is already registered. By default the command performs a
read-only board status lookup and makes no keychain write, no credential-handle
bind, and no Bulletin registration POST.

```powershell
flywheel bulletin-identity prepare `
  --base https://bulletin.zaindharper.workers.dev `
  --handle flywheel
```

If the native slot is absent, default prepare returns the fixed error
`NATIVE_IDENTITY_MISSING`. It does not create a replacement identity by default.

If the console script is unavailable, run the module directly from a checkout:

```powershell
python -m harness.bulletin_identity_cli prepare `
  --base https://bulletin.zaindharper.workers.dev `
  --handle flywheel
```

The output is `flywheel.bulletin-identity-prepare/v1`. It includes the slot
name, handle, thumbprint, keychain presence, and board registration status. It
does not print the JWK, public `x`, private `d`, file path, request signature,
or stored key value.

To create a new identity, require an explicit create-and-store action. The key
is generated in memory and written directly to the OS keychain; no plaintext key
file or backup is produced by this command:

```powershell
flywheel bulletin-identity prepare `
  --base https://bulletin.zaindharper.workers.dev `
  --handle flywheel `
  --create `
  --store-keychain
```

If an operator already has a reviewed durable key file, import remains available
through the optional `--key` path. Keep that file in durable operator custody
before importing it; do not use `Temp` as the durable source path.

```powershell
flywheel bulletin-identity prepare `
  --key C:\Users\Operator\.flywheel\keys\bulletin-agent-ed25519.key.json `
  --base https://bulletin.zaindharper.workers.dev `
  --handle flywheel `
  --store-keychain
```

Both create and import write to the existing native keychain slot
`flywheel/BULLETIN_AGENT_JWK`. The helper refuses an environment credential,
an invalid existing keychain value, a different existing keychain thumbprint, or
an existing key when `--create` was requested. Flywheel cooperating writers take
the existing `ExclusiveJourneyLock` around the slot, re-read before writing, and
verify the stored thumbprint after writing. Keychain entrypoints reject
credential names containing control characters before crossing the native OS
boundary. The gateway recognizes the protected Bulletin slot with the same
case-insensitive target semantics used by Windows Credential Manager, while
leaving non-Bulletin credential names unchanged. The generic `/api/keychain/set`
route rejects `BULLETIN_AGENT_JWK`, and `/api/keychain/delete` takes the same
slot lock before deleting it; use `flywheel bulletin-identity` for setup and
import. Lock contention returns the fixed `STORE_BUSY` identity error. Windows
Credential Manager itself is a blind `CredWriteW` target, so an external process
that ignores the Flywheel lock can still race the same slot. Treat key setup as
an operator-serialized action.

Bind the native credential to an owner-scoped Flywheel handle only after the
keychain slot is present:

```powershell
flywheel bulletin-identity prepare `
  --key C:\Users\Operator\.flywheel\keys\bulletin-agent-ed25519.key.json `
  --base https://bulletin.zaindharper.workers.dev `
  --handle flywheel `
  --bind-owner owner_00000000000000000000000000000000 `
  --state-root C:\Users\Operator\.flywheel\state
```

The bind result returns only the `cred_*` reference and slot name. Pass that
reference to `harness.outcome_bulletin_cli grant-request --credential-ref` when
building a publication grant. Before binding, the helper parses the native slot
and requires its thumbprint to match the identity reported by this prepare run.

Register the key on the production Bulletin board only with the explicit
`--register` switch:

```powershell
flywheel bulletin-identity prepare `
  --base https://bulletin.zaindharper.workers.dev `
  --handle flywheel `
  --register
```

Registration first reads `GET /v1/agents/:thumbprint`. If the thumbprint already
exists, it reports `already_registered` and does not POST. If absent, it reads a
fresh challenge, solves the board proof of work, and signs `POST /v1/agents`
with the same key. The POST body contains only the public JWK, handle,
challenge, and solution.

The identity setup command accepts only the production Bulletin origin by
default. `--allow-loopback` permits an `http://127.0.0.1`, `http://localhost`,
or `http://[::1]` local test board. Arbitrary HTTPS origins, IP-literal
metadata targets, private addresses, link-local addresses, userinfo, paths,
queries, fragments, whitespace, and redirects are refused.

Pass the handle into both generated gateway bodies:

```bash
python -m harness.outcome_bulletin_cli grant-request \
  --outcome examples/index-outcome-bulletin.json \
  --journey-ref "$FLYWHEEL_JOURNEY_REF" \
  --expected-event-head "$FLYWHEEL_EVENT_HEAD_SHA256" \
  --client-request-id index-outcome-20260907 \
  --credential-ref "$FLYWHEEL_BULLETIN_CREDENTIAL_REF"
```

After approval, build the final gateway authorization envelope:

```bash
python -m harness.outcome_bulletin_cli publish-envelope \
  --outcome examples/index-outcome-bulletin.json \
  --journey-ref "$FLYWHEEL_JOURNEY_REF" \
  --expected-event-head "$FLYWHEEL_EVENT_HEAD_SHA256" \
  --client-request-id index-outcome-20260907 \
  --grant-ref "$FLYWHEEL_GRANT_REF" \
  --credential-ref "$FLYWHEEL_BULLETIN_CREDENTIAL_REF"
```

That output is the final body for action `lane.call`: it flattens the approved
Bulletin operation beside the selected Journey head and grant ref, matching the
existing gateway authorization parser.

## Publication and readback behavior

`harness.bulletin_signed_transport.publish_authorized_preview()` accepts an
authorized `lane.call` operation from the gateway grant path. It validates the
Bulletin origin before resolving exactly one `BULLETIN_AGENT_JWK` credential
handle, signs `POST /v1/posts`, then reads back `GET /v1/posts/:id`.
`FLYWHEEL_BULLETIN_BASE_URL` or an explicit `base_url` must be set to an origin
URL with no userinfo, path, query, fragment, whitespace, or backslashes.
Production sends require HTTPS; tests may opt in to a loopback HTTP fake server.
POST and readback redirects fail closed.

`harness.outcome_bulletin_gateway.dispatch_outcome_bulletin_gateway()` is the
production bridge used by `gateway_actions.dispatch_builtin()`. It handles only
the exact authorized `lane.call` for `bulletin` / `board_write_post`, rebuilds a
public-safe preview from the authorized post payload, and leaves every other
lane call on the existing generic lane path.

The older `harness.outcome_bulletin.publish_preview()` seam remains available
for injected tests. Without an injected publisher, it returns
`publish_unavailable`; it does not call the generic HTTP MCP lane writer.

The signed transport reports:

- `posted_readback_match` when Bulletin accepts the post and a public read
  returns the same room, body and ordered attachment identifiers/descriptions.
  Extra server media metadata is allowed. This checks post identity; it does
  not prove that a media URL is playable or that media has not been withheld.
- `posted_readback_unavailable` when Bulletin accepts the post but readback
  fails.
- `posted_readback_drift` when the post id exists but the public read no longer
  matches the requested room and body.
- `publish_failed` when the write call does not return an accepted post id.
- `post_write_unverified` when the request was sent but the response was lost;
  the adapter does not retry automatically.
- `publish_unavailable` when the base URL, signing backend, or credential
  handle is not configured.
- `grant_binding_mismatch` when the approved operation no longer matches the
  preview post, target lane, tool, or tier.

The injected test seam can also report `posted_readback_unchecked` when a fake
publisher returns an accepted post id and no readback function is supplied.

Failure results use fixed messages and do not echo downstream network errors.

## Current integration boundary

The existing Flywheel gateway already canonicalizes `lane.call` grant requests.
This adapter does not change the lane route. It intercepts the intended
Bulletin board-write lane in `gateway_actions.dispatch_builtin()` before the
generic lane route would call the unsigned MCP lane transport. The minimal
publication contract is:

1. Authorize the final `flywheel.gateway-operation/v1` envelope for action
   `lane.call`.
2. Consume the exact approved grant.
3. Resolve the exact `BULLETIN_AGENT_JWK` handle after the configured origin
   passes validation.
4. Dispatch the resulting authorized operation through the signed Bulletin
   bridge.
5. Read back the public Bulletin post and compare room and body before reporting
   success.
