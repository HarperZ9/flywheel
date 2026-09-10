# Strict local HTTP transport

Local endpoint evaluation can inject a restricted transport without changing
the existing backend protocol or the default CLI. It binds one numeric loopback
HTTP origin and a set of exact method/path pairs. Example for a Serve backend:

```python
from harness.strict_local_http import StrictLocalHTTPPolicy, make_strict_local_http
from harness.model_endpoint_gate_cli import build_report

transport = make_strict_local_http(StrictLocalHTTPPolicy(
    origin="http://127.0.0.1:8080",
    allowed_routes={("GET", "/health"), ("POST", "/generate")},
    max_timeout_seconds=30,
))
report = build_report(profile_artifact="profiles.json", models=[], backends=[],
                      transport=transport, timeout_seconds=30)
```

The gate forwards this same four-argument callable to health and generation.
For Ollama, admit `GET /api/tags` and `POST /api/chat` instead. Health's caller
timeout remains five seconds; each caller can shorten the policy deadline.
No CLI, actor, or smoke path obtains these bounds unless it injects the callable.
Existing transport defaults and HTTPS support elsewhere remain unchanged.

## Bounds

Only a canonical numeric loopback address with an explicit port is accepted.
The connection uses that address directly, without DNS resolution, environmental
proxies, redirects, retries, tunnels, or alternate destinations. Paths cannot
contain queries, fragments, percent escapes, dot segments, or ambiguous slashes.
The strict policy supports HTTP only.

Policy byte caps must be positive integers below the platform's `sys.maxsize`;
the timeout cap must be positive, finite and at most 86,400 seconds (one day).
These validation bounds prevent integer and platform timeout overflow. A caller's
larger finite timeout is shortened to the admitted policy cap.

The default encoded request body cap is 256 KiB. The default received HTTP wire
cap is 1 MiB, including status lines, headers, and chunk framing. This leaves less
than 1 MiB for the JSON body; it is not a bound on all Python process memory.
Responses use the existing strict JSON-object parser, which also rejects
duplicate keys, nonfinite numbers, excessive depth and oversized string fields.
Success and error responses have the same bounds. Redirect responses fail.

One absolute monotonic deadline covers blocking connect, send, status/header,
body and chunk reads, including trickling traffic. Each blocking socket operation
uses the remaining time. Parsing is checked before and after; normal scheduler
and cleanup overhead still applies. A client timeout does not prove that backend
computation stopped. This transport is not a host firewall or model sandbox.

## Optional observation

Pass `observer=record` to the factory to receive content-free dictionaries.
The observer is trusted synchronous application code and must return promptly.
Socket deadlines cannot preempt a hanging recorder. After callbacks, the deadline
is checked before further network I/O. Terminal recorder latency does not
reclassify already completed network work. No recorder threads are started.

Every admitted call has a fresh UUID `attempt_id`. Events contain exactly:

| Field | Meaning |
| --- | --- |
| `phase` | `connection_attempt`, `request_send_started`, or `terminal` |
| `attempt_id` | Correlation within this callable entry |
| `method`, `path` | Admitted pair; no full URL or body |
| `connection_started` | A connect syscall has been attempted |
| `request_send_started` | A request send syscall has been attempted |
| `outcome` | Terminal `response`, `error`, or `timeout`; otherwise null |
| `code` | Fixed local terminal code; otherwise null |
| `status` | HTTP status for a complete parsed response; otherwise null |

Connection and first-send events are intent markers emitted before their syscall.
Their booleans describe prior attempted operations. The corresponding boolean
becomes true only after the callback and deadline checks, immediately before I/O.
The first-send marker occurs once even when headers and body use separate sends.
Only the terminal snapshot describes final local progression. An attempted send
does not prove bytes arrived, a generation was accepted, or a task succeeded.
GET metadata calls remain distinguishable from POST generation calls by route.
No token usage or durable recording is inferred.

Preflight denials emit no network events. Callers must count callable entries
separately from connection/send intent or progression. An observer's return value
and mutations to its dictionary cannot alter the request. Recorder exceptions
prevent the next I/O operation and produce `observer_failed` without retrying the
request or calling the failed recorder again.

`StrictLocalHTTPError` derives from `OSError`; its fixed `code` and optional
`terminal_event` contain no raw exception text. `StrictLocalHTTPTimeout` is also
a `TimeoutError`. Preflight failures have `terminal_event=None`. Other failures
retain an in-memory terminal snapshot even if its recorder failed. A true
`request_send_started` means delivery remains possible; it must not be reported
as prevented delivery. An in-memory snapshot is not a persisted receipt.

Owned loopback controls cover receive/send deadlines, wire caps, invalid routes,
proxy/redirect isolation, malformed responses, gate injection, observer failures,
and receiving-side request counts. They do not evaluate a model's behavior or
establish host-wide network containment.
