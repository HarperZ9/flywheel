# Frozen Studio Gateway Smoke Helper

Status: wired into `scripts/check_frozen_gateway.py`; actual Windows executable
acceptance passed on 2026-09-15. Installer and UI acceptance remain separate.

## Purpose

Add a bounded acceptance helper for the frozen gateway's Studio body routes. The
helper gives the release checker a focused way to prove that the packaged
gateway can enforce bearer custody, expose an honest Studio status document,
refuse an ungranted Studio action, accept one explicitly granted Studio Engine
render action, and independently verify the returned PNG frame hashes.

This is not an installer, UI, live-capture, provider, network, or installed-use
claim. It is a loopback HTTP probe against the gateway executable that root will
start separately.

## Owned files

- `scripts/frozen_gateway_studio_smoke.py`
- `scripts/frozen_gateway_studio_contract.py`
- `tests/test_frozen_gateway_studio_smoke.py`
- `tests/frozen_studio_fixtures.py`
- `project-docs/specs/SPEC-frozen-studio-smoke-20260915.md`

Root owns wiring this helper into `scripts/check_frozen_gateway.py` and running
it against the actual frozen executable.

## Acceptance behavior

The helper prepares an isolated Accountable Surface authority fixture and refuses
to overwrite pre-existing authority files:

- `ACCOUNTABLE_SURFACE_GRANTS`
- `ACCOUNTABLE_SURFACE_AUTHORITY_STATE`
- `ACCOUNTABLE_SURFACE_JOURNAL`

The grant permits exactly one `flywheel.studio.engine.render-world/v1` action
for `flywheel://studio/engine/session-1/visual-1`, with the Studio Engine API
bound. Its read scope names the exact Studio Engine resource
`/engine/session-1/visual-1` rather than a broad engine path pattern.

```json
{"kind":"api","origins":["flywheel://studio"],"intents":["render_world"]}
```

The smoke then uses gateway HTTP callbacks only:

1. `GET /api/studio/body/status` without a bearer token must return
   `AUTH_REQUIRED`.
2. Authenticated `GET /api/studio/body/status` must advertise the Studio body
   contract, configured Accountable Surface authority, an unverified grant until
   step execution, and no backend-ready claim before a step is accepted.
3. Authenticated `POST /api/studio/body/step` with an ungranted sound action
   must be refused with HTTP 403.
4. Authenticated `POST /api/studio/body/step` with a syntactically valid
   render-world action for `flywheel://studio/engine/session-1/visual-2` must
   be refused with HTTP 403, `accepted=false`, no receipt, and no acted
   authority receipt.
5. Authenticated `POST /api/studio/body/step` with the bounded render-world
   action must return `accepted`, `decision=allow`, `acted=true`,
   `verified=true`, and `usage_counted=1`.
6. The helper decodes each returned PNG frame and checks the computed SHA-256
   against `frame_sha256`; a corrupted returned hash fails closed.
7. The helper treats each frame's `sha256` field as the Studio Engine legacy
   16-hex artifact id and checks it for membership in the typed list
   `engine_receipt.artifact_shas`. Missing or malformed artifact ids, missing
   artifact lists, and non-members fail closed. Full PNG byte integrity remains
   bound to `frame_sha256`.
8. A second distinct render-world step must be refused with HTTP 403, proving
   the one-use grant is exhausted after the accepted action.

The returned summary is compact, exact-key validated, and omits bearer tokens,
local paths, raw frames, full receipts, and secret-bearing response bodies. It
sets `exact_scope_checked=true` only after the off-target render probe receives
the required refusal. It explicitly declares `semantic_render_criteria` as
unverified; this smoke checks transport, authority, exact target/read scoping,
refusal, one-use exhaustion, and PNG byte binding, not visual semantics.

## Integration call signature

Root should create the Studio fixture before starting the frozen gateway, merge
its environment into the checker's isolated runtime environment, then run the
acceptance smoke after the bearer token is available:

```python
from scripts.frozen_gateway_studio_smoke import (
    prepare_studio_smoke_fixture,
    run_studio_acceptance_smoke,
)

studio_fixture = prepare_studio_smoke_fixture(home)
env.update(studio_fixture.env)

receipt["studio_acceptance"] = run_studio_acceptance_smoke(
    base, token, studio_fixture)
```

The helper also exposes `validate_studio_smoke_summary(summary)` for receipt
validation.

## Does not prove

- Installer installation or clean-OS compatibility.
- Flutter UI rendering.
- Live screen capture correctness.
- Provider/model-backed execution.
- Public release, external adoption, or installed production use.
