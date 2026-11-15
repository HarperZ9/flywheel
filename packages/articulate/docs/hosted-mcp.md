# Opt-in hosted MCP design and acceptance record

Status: implemented with local HTTP acceptance tests; no hosted deployment or
native-client acceptance. The package version has not changed for this work.

Release direction: local self-hosting is the default. The external-issuer HTTP
mode documented here is an advanced option. Normal local stdio operation must
not require a cloud host, public domain or external identity provider. Integrated
runtime packaging and local pairing remain release work; the authentication in
this HTTP mode remains enforced.

The selected release option adds a hosted MCP resource server for clients that
cannot launch local processes. Submitted text leaves the client and reaches the
operator's service. The calling model writes proposed edits; the service runs
the existing detector, host edit plan and host submission checks in memory.
This does not establish semantic equivalence or factual correctness.

## Design and implementation plan

The explicit `python -m articulate.hosted_mcp` entrypoint uses the optional
`hosted` extra. The default install remains standard-library-only. It exposes
only `check`, `score`, `edit_plan`, and `edit_submit` over stateless HTTP at
`/mcp`. It has no backend selector, sampling, subprocess, filesystem path,
custom profile, local configuration, account-creation or deployment tool.

Authentication uses FastMCP `RemoteAuthProvider` and `JWTVerifier`: a configured
external OAuth server issues RS256 tokens; the resource server checks signature,
issuer, resource audience, mandatory finite future expiry and the
`articulate:use` scope.
Protected-resource metadata and 401 challenges advertise the OAuth server.
There is no anonymous startup mode. Production configuration requires HTTPS
issuer, JWKS and public base URLs. Binding defaults to loopback; TLS termination
and OAuth registration remain infrastructure responsibilities.

The ASGI boundary caps request bytes before JSON parsing, rejects compression,
caps simultaneous requests and applies a process-wide request budget. This
budget deliberately does not retain client identity, IP addresses or tokens.
Tool text and plan fields have character limits and reject extra parameters.
Application boundary errors use fixed messages; SDK tool errors are masked.
Application HTTP responses carry `Cache-Control: no-store`.
Request-scoped log redaction removes message,
arguments and exception details from Python logging while requests run,
including worker contexts. No application request-body store or edit history
is created. These controls make no promise about client, provider, reverse
proxy, host memory, crash dumps or external logging systems.

Files and execution order:

1. Add `tests/test_hosted_mcp.py` with signed ephemeral tokens and real ASGI HTTP
   calls. First observe failure because the hosted module does not exist.
2. Add `src/articulate/hosted_mcp.py` for validated configuration, vetted auth,
   four bounded tools, and the explicit entrypoint. Add
   `src/articulate/hosted_boundary.py` for ingress limits and log redaction.
3. Run the focused HTTP tests: missing/invalid/wrong issuer/wrong audience,
   expired/missing expiry/scope, metadata/challenge, valid check/plan/submit,
   extra backend/path fields, malformed/oversize requests, rate/concurrency,
   and source-body log leakage. Preserve negative results in the report.
4. Add the `hosted` optional dependency and a placeholder-only deployment
   environment example. Document remaining infrastructure/client acceptance.

Review focus: unsigned or wrong-resource credentials; unexpected body logging;
custom settings smuggled through plan tokens; oversized/chunked input; false
claims of end-to-end privacy or native-client acceptance.

References consulted for this design: [FastMCP Remote OAuth](https://gofastmcp.com/servers/auth/remote-oauth),
[FastMCP token verification](https://gofastmcp.com/servers/auth/token-verification),
and [OpenAI plugin authentication](https://developers.openai.com/plugins/build/auth).
Implementation is checked against installed FastMCP 3.2.4 and MCP 1.27.0 APIs.

## Operator setup

The hosted extra requires Python 3.10 or later. The base detector still supports
Python 3.9 without the hosted dependencies. Install from a reviewed source
checkout or a release containing this module:

```sh
python -m pip install ".[hosted]"
```

Use [the environment example](../examples/hosted-environment.example) to
configure a service manager. Articulate does not load that file. The values are
public identifiers; do not put bearer tokens, signing keys or OAuth client
secrets in it.

- `ARTICULATE_HOSTED_BASE_URL`: public HTTPS origin, such as
  `https://articulate.example`.
- `ARTICULATE_HOSTED_ISSUER`: exact issuer identifier from the external
  authorization server.
- `ARTICULATE_HOSTED_JWKS_URI`: trusted public HTTPS JWKS endpoint for that issuer.
- `ARTICULATE_HOSTED_BIND`: bind address; defaults to `127.0.0.1`.
- `ARTICULATE_HOSTED_PORT`: bind port; defaults to `8765`.

The base origin must use canonical URL spelling: lowercase host and no explicit
default `:443` port. A trailing slash is accepted. This keeps discovery metadata
and the token audience consistent. The issuer spelling is exact, including any
trailing slash. The required token
audience is the base origin followed by `/mcp`. The token must be signed with
RS256 and include the `articulate:use` scope and a future `exp` claim. There is no
environment setting to disable authentication. Static public keys are supported
by the Python configuration API for tests and operator integrations; the CLI
requires a JWKS URL.

After the operator has arranged OAuth and TLS, the explicit launch command is:

```sh
python -m articulate.hosted_mcp
```

The command binds to loopback by default. Keep the application listener behind
an HTTPS reverse proxy. Forward the `Authorization`, `Accept` and MCP protocol
headers and preserve `/mcp` and `/.well-known/oauth-protected-resource/mcp`.
Disable request body logging, token logging, response caching and debug tracing
at the proxy, service manager and monitoring agents. Configure request/header
size limits, connection deadlines and abuse limits at that boundary too. The
application disables Uvicorn access logs and ignores forwarded proxy headers.

This module is an OAuth resource server. The external authorization server must
support the intended client's registration and authorization flow and issue the
required audience and scope. Articulate does not create accounts, register OAuth
clients, provide a consent page or issue tokens. Protected-resource discovery
and an authenticated test token establish the server contract; they do not
establish that a native client can complete its authorization flow.

## Limits and deployment tradeoffs

Default bounds per application process are 262,144 request bytes, 20,000
characters per text field, 16,000 plan characters, four concurrent requests,
120 admitted requests per rolling minute and ten seconds to receive a body.
Compressed bodies are rejected. The request budget includes unauthenticated
requests and metadata discovery. A caller can exhaust that shared budget;
identity-aware fairness belongs at the operator's external boundary. Separate
workers or replicas each have their own budget, so scaling them also increases
the aggregate limit. The CLI launches one worker. The concurrency cap counts
active HTTP requests inside the application, including requests awaiting a body.
Idle keep-alive connections do not consume that budget. Apply connection-count
limits at the reverse proxy; Uvicorn's connection-based concurrency switch is
left unset so pooled idle connections cannot bypass the application with a 503.

The Python `HostedConfig` API can change bounds. Higher limits increase memory
and CPU exposure; these tests do not establish production capacity or a hard
deadline for detector execution. Slow body reads time out, but synchronous
detector work already running in a worker thread cannot be forcibly cancelled.
The service keeps request bytes and tool results in process memory during
handling, with no application history or database. Token verification can fetch
public signing keys from the configured JWKS endpoint. Python log redaction
does not control direct output streams, third-party telemetry, process dumps,
swap, clients or infrastructure logs.

The service shares the detector and protected-span checks with local Articulate.
An accepted edit can still be wrong. Custom profile objects, filesystem paths,
backend selectors and extra tool parameters are rejected. Plan checksums are
public integrity values, not credentials: a client can construct one, so submit
also verifies that its settings match a packaged mode or profile.

## Verification and release boundary

From the checkout:

```sh
python -m pip install -e ".[dev,hosted]" httpx
python -m pytest tests/test_hosted_mcp.py -q
```

The local Python 3.12 run passed 47 tests with FastMCP 3.2.4 and MCP 1.27.0.
Tests call the real ASGI transport using ephemeral signed test credentials.
They exercise authentication failures, discovery, tool descriptors, the four
tools, source-log redaction, request limits, distinct ASGI chunks, slow body
timeouts, concurrency and forged plan
settings. The tests found missing cache controls on successful responses and an
SDK exception for a signed infinite-expiry token. Both now have regression
controls. Independent review also found noncanonical base origins disagreeing
with discovery metadata and an extra Uvicorn connection cap rejecting valid
requests before the application ran. Canonical-origin validation and a single
application request cap address those findings. Regression tests use Uvicorn's
H11 protocol and an in-memory transport to check the actual entrypoint options
with one and four open connections, without opening a socket.
These counts describe the focused HTTP suite. Full release validation
is a separate gate.

The dedicated `hosted.yml` CI workflow installs the hosted extra and imports the
transport dependencies before running the suite on Python 3.10 and 3.12. Its
configuration is checked in; a passing remote run remains a separate receipt.
Base-only environments skip these HTTP tests.

Before public operation, retain receipts for the chosen authorization server's
JWKS key rotation and native-client authorization, HTTPS routing, proxy logging
settings, abuse/load behavior and the operator's disclosure of submitted-text
handling. No live OAuth server, public listener, hosted account, deployment or
native-client connection was created by this implementation. Hosting remains an
explicit operator choice.
