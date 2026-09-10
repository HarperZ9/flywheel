# Telos browser adapter, stage 1

This optional adapter reuses the existing Telos CDP client to read bounded page
text and request navigation on one configured target. It never starts a browser,
searches for a default tab, enters credentials, runs caller JavaScript, or exposes
Telos device commands. It is an intermediate step toward the broader computer
control workflow, with synthetic source controls and real runtime acceptance
still separate.

## Explicit configuration

`harness.telos_browser_registration.configure_telos_browser(config_path)` loads
one explicitly supplied JSON file. There was no existing browser configuration
contract to extend. The planned gateway hook supplies
`FLYWHEEL_TELOS_BROWSER_CONFIG`; absent or invalid configuration remains
unavailable. Registration means configured, not runtime verified. The session
binding and gateway hook are a separately reviewed integration prerequisite:
the adapter cannot register against the older two-argument driver seam.

Reconfiguration first unregisters only `telos-browser`, preserving other
registrations. Missing or invalid replacement configuration cannot retain the
previous driver for later dispatch. Concurrent configure calls are serialized.
Removal cannot cancel a callable already captured by an in-flight attempt; that
attempt remains governed by its persisted admission and live adapter checks.
If registry removal fails or the required removal seam is absent, availability
is explicitly unknown (`null`), not falsely reported disabled.

The file has exactly these keys:

| Key | Required value |
| --- | --- |
| `schema` | `flywheel.telos-browser-config/v1` |
| `node_path` | Absolute path to an existing trusted Node executable with native fetch and WebSocket support |
| `cdp_module` | Absolute path to the existing Telos `demo/native-control/cdp.mjs` |
| `cdp_sha256` | SHA256 of that file's exact bytes |
| `port` | Explicit integer debugger port on `127.0.0.1` |
| `browser_instance` | Observed `/devtools/browser/<opaque-id>` path from the existing debugger |
| `target_id` | Exact observed page target ID, never a URL/title substring |
| `allowed_origin` | One canonical HTTP(S) origin without credentials, path, query or fragment |

Use an existing authorized observation to supply the browser instance and target
ID. This implementation does not discover a default, launch a profile, or invent
an observation. Current discovery must find exactly one target with that ID,
the expected debugger socket path and the allowed page origin. Browser identity
and target selection are checked again after connecting. The main-frame origin
is checked before an operation. Wrong, missing, duplicate or replaced identities
are rejected. These are snapshots, not a lock against concurrent navigation.

Only the reviewed Telos CDP module from commit `b53daedf` is admitted. Its
normalized-LF SHA256 is
`d2d43363842b3f84e4f4562c6f7d74c1ff0d98054c456c172d9a0e70db9b1413`.
That module has no imports; LF and CRLF copies are accepted while the configured
raw-byte hash is also checked. Other Telos versions require source review and
a deliberate pin update. This verifies that module, not Node, Chrome, or the
host. Runtime hash checks are not atomic protection from a hostile local
administrator swapping files between checking and importing them.

## Admission and results

The immutable descriptor produces `binding_sha256`. Registration passes it to
the browser admission layer. That layer must retain the binding in the session
policy and reject a different binding before dispatch; its durable request ID
and intent record must precede the adapter call. The digest provides continuity,
not independent truth or permission.

The adapter returns `performed: true` only for a valid acknowledgement from its
real configured process. Injected test launchers return `fixture_only` with
`performed: false`. A known refusal before a page operation reports no
performance. Missing, malformed, late or contradictory replies and uncertain
cleanup raise a fixed unknown-delivery error. There are no retries.

Reads use one fixed expression in an isolated main-frame context and check the
origin inside that context. The adapter returns at most 16 KiB of text. Text is
still private page content; it is not automatically public evidence. The existing
browser API stores result hashes, so native observation display remains required
before this is a usable end-to-end reading interface.

Navigation only accepts a destination on the configured origin. Its
`navigation_requested` result means CDP acknowledged the request, not that the
page loaded, stayed on that origin, or completed a task. Redirects are detected
by the next origin check. This is not an egress firewall for navigation or page
subresources. The protocol semantics are described in the
[CDP Page reference](https://chromedevtools.github.io/devtools-protocol/tot/Page/).

## Bounds and release boundary

The adapter reuses Flywheel's suspended Windows process and Job Object runner,
with an explicit hidden-window option. It uses a minimal environment and fixed
argv with no shell. Node options and proxy/credential environment variables are
not inherited. Other platforms remain unavailable through this runner.

- Configuration and request: 16 KiB each; accepted result: 32 KiB.
- Debugger HTTP response and accepted WebSocket message: 256 KiB each.
- Retained process capture: 1 MiB of bytes per stdout/stderr stream.
- Owned-process wait deadline: at most 10 seconds, measured before launch,
  with a shorter Node deadline. Trusted preflight filesystem calls and the
  operating system's process-creation call cannot be forcibly preempted here.
  Overflow is polled at up to 20 ms intervals while waiting; owned cleanup is
  requested on timeout or either capture limit. Scheduling and bounded cleanup
  can add latency. This is not an instantaneous kill or zero-extra-output claim.

The native WebSocket can allocate an incoming frame before the application sees
its size. Process capture is bounded; this is not a heap-memory sandbox. Error
messages never include raw stderr, debugger URLs, page text or local paths.

Run the isolated checks with:

```
python -m pytest tests/test_telos_browser_adapter.py tests/test_telos_owned_launch.py tests/test_telos_browser_bridge.py -q
```

They use fake processes and protocol responses. They do not launch or drive a
browser, enumerate windows, call models or establish real-world task success.

Remaining acceptance work is explicit: reviewed session binding and gateway
registration; an owned-page read/navigation E2E; bounded native observations;
observed-element click/input with credential checks and document continuity;
denied-but-applied controls; screenshots with privacy handling; replacement and
navigation recovery; then desktop workflow acceptance. No installed replacement,
superiority, alignment or safety guarantee follows from this stage.
