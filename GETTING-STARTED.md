# Getting Started with Flywheel

> Your first thirty minutes with the accountable agent platform.

## What Flywheel is

Flywheel is the accountability infrastructure for agentic AI. Every tool call
an agent makes carries a sealed receipt. Every system is classified by
consequence (TADR T1/T2/T3). Every divergence becomes a lesson the
organization remembers. The receipts make the remembering trustworthy.

**The theory.** Nothing self-warrants. Every property worth trusting is
conferred by something outside the thing itself, witnessed, coverage-accounted,
stamped MATCH / DRIFT / UNVERIFIABLE. This is the witnessing spine, and it
holds across every layer of the platform.

## Release status

Use [v1.0.0](https://github.com/HarperZ9/flywheel/releases/tag/v1.0.0) for the
currently published install path. This source checkout now declares
`1.0.0` for the candidate line, and [RELEASE-NOTES-1.0.0.md](RELEASE-NOTES-1.0.0.md)
lists the remaining release holds. A source checkout is a development path, not
a published 1.0 artifact.

## Install

```bash
python -m pip install flywheel-verify==1.0.0
```

(`flywheel-verify` is the PyPI distribution name; the installed command is
`flywheel`. From a source checkout for candidate development: `pip install -e .`.)

Zero runtime dependencies. Python 3.11+. Stdlib only. No model download is
required: the engine works immediately against any hosted provider you hold a
key for, and local models are an optional layer (ollama needs no extras; the
published 14B/32B weights are separate downloads). Optional extras provide the
third-party packages some paths need, and are never required:

```bash
pip install "flywheel-verify[signing]"   # receipt signing (verification stays stdlib)
pip install "flywheel-verify[monitor]"   # network egress monitoring
pip install "flywheel-verify[local]"     # the local HF serve/training stack
```

## Sign in with a subscription

A token an authorized login already produced can carry your usage instead of a
raw API key. Each provider differs in what it permits, and the CLI says which
is which rather than implying they are alike:

```bash
flywheel auth status              # presence and terms per provider
flywheel auth login openrouter    # OpenRouter documents this third-party PKCE
                                  # flow; no registration needed
flywheel auth login anthropic     # guided: the official `claude setup-token`
                                  # mints the token and you paste it once.
                                  # flywheel runs no OAuth client of its own
                                  # and claims no provider sanction; what the
                                  # token may be used for is governed by
                                  # Anthropic's terms, which you accept
flywheel auth login openai        # needs an app registration you own; set
                                  # FLYWHEEL_OPENAI_OAUTH_CLIENT_ID plus
                                  # _AUTHORIZE_URL and _EXCHANGE_URL
```

The desktop app has the same thing with buttons: **Endpoints → sign in**,
one row per provider with its terms stated, a Sign in button for the browser
flow, and an obscured paste field for the provider-tool flow.

Tokens land in the OS credential store under the same names the router
already reads, so a completed sign-in shows up on the endpoints roster
(presence only, never values). Sign out with
`flywheel auth logout <provider>`; if the token is also set as an environment
variable, the command says so instead of claiming it cleared it.

Two guarantees hold across every flow: the engine never runs another app's
OAuth client, and it refuses to start a flow on a machine with no credential
store rather than minting a token it cannot keep. Provider terms are yours to
read; flywheel does not interpret them for you.

## Start the engine

```bash
flywheel app --port 8799
```

(From a source checkout: `python scripts/run_harness_cli.py app --port 8799`.)

The gateway serves on `http://127.0.0.1:8799` (localhost only). The Flutter
desktop client connects automatically when launched.

## Start the desktop client

Download the current published installer,
[Flywheel-Setup-1.0.0-x64.exe](https://github.com/HarperZ9/flywheel/releases/download/v1.0.0/Flywheel-Setup-1.0.0-x64.exe),
and verify it against the release
[SHA256SUMS.txt](https://github.com/HarperZ9/flywheel/releases/download/v1.0.0/SHA256SUMS.txt)
(engine bundled, no Python needed). From a candidate source checkout:

```bash
cd desktop && flutter run -d windows
```

The desktop client shows its destinations in a collapsible side rail,
grouped into Work, Chat, Code, Evidence, and Advanced. Type in the rail's
search field to filter it. Or press Ctrl+K to open the command palette and
jump to any destination by name.

## Ownership, profiles, memory, and sessions

This section describes behavior in the current candidate source unless a release
note says otherwise. The published 1.0.0 installer remains the install target
above, and not every native candidate behavior described here ships in 1.0.0.

Flywheel binds native state to configured local ownership, project, workspace,
and session facts instead of a display name. The desktop asks the local gateway
which Canon project and workspace are configured, then uses that binding for
context memory. Retrieved memory is input data; the run still needs its own
receipts and evidence before a result is accepted.

Native provider sessions are scoped to one run and one reviewed profile. The
restricted-files direct CLI adapter binds the selected provider profile,
workspace, account readiness, tool grants, and budget before launch; the exact
limits are documented in
[docs/native-cli-session-contract.md](docs/native-cli-session-contract.md). That
contract refuses the older direct Codex CLI path because it lacked an admitted
project-isolation control. It does not rule out separate managed provider-session
candidate work on the 1.0 line.

Continuation starts a fresh Evidence Journey from a source-bound workspace or
export preview and refuses source drift; it does not resume a provider-native
web session. Writing Workspace binds author state to the configured Flywheel
home and keeps proposal approval on an operator-controlled surface. The detailed
native feature docs are [desktop/README.md](desktop/README.md),
[docs/CONTEXT-MEMORY.md](docs/CONTEXT-MEMORY.md),
[docs/native-continuation.md](docs/native-continuation.md), and
[docs/writing-workspace.md](docs/writing-workspace.md).

## Meet Rowan

Rowan is the assistant that operates Flywheel, and the face and voice of the
app. Open Chat and ask for work in plain words. Rowan turns the request into a
task the app runs and keeps a record of. It can start a run for you and read
back tasks the gateway already holds, so you can see where each one stands. You
can also drive every surface yourself, and the run leaves the same record.

Rowan runs on the model you choose, local or hosted, and it is openly an
assistant. It does not present as a human or as a specific model, and the model
selector always shows the one in use. If a submission gets lost, Rowan reports
it and does not resend on its own. A result the recheck cannot confirm stays
marked that way.

The avatar beside the chat is drawn live on your machine. It is a rendered
visual, and it makes no claim about any model. The first time you open the
desktop client, a short walkthrough introduces Rowan and the rest of the app.

## Your first receipt

```python
from harness.tool_call_receipt import build_receipt, verify_receipt

receipt = build_receipt(
    tool="read_file", capability="builtin-read", admission="ALLOWED",
    args={"path": "/tmp/config.yml"}, output="db_url: localhost",
    ok=True, rc=0, run_id="my-first-run", seq=0,
)
print(f"seal: {receipt['seal']['hex'][:16]}...")

v = verify_receipt(receipt)
print(f"verdict: {v['verdict']}")  # MATCH
```

The receipt binds what was called, what was allowed, what happened, and why.
A stranger re-walks the chain offline. This is the enforced AgentRiskBOM.

## Your first governance classification

```python
from harness.governance.tadr_tier import classify
from harness.governance.control_baseline import check_compliance

# Classify a system by its consequences
result = classify(
    consequence_overrides=["multi-site-disruption"],
    assessment={"consequence_magnitude": "severe"},
    modifiers=["A", "D"],
)
print(f"tier: {result.label()}")  # T2-A/D

# Check control baseline compliance
report = check_compliance("T2", has_tamper_evident_logs=True)
print(f"compliant: {report.compliant}")  # True or False
print(f"missing: {report.failed} controls")
```

The no-inflation gate prevents a T1 system from performing T3 actions. The
governance envelope carries tier + compliance state across all lanes.

## Your first signed receipt

```python
from harness.crypto.signatures import generate_keypair, wrap_signed, verify_signed

priv, pub = generate_keypair()
lesson = {"schema": "flywheel.lesson/v1", "claim": "drift detected"}
signed = wrap_signed(lesson, priv)
result = verify_signed(signed)
print(f"verdict: {result['verdict']}")  # MATCH
```

The ed25519 signature is detached and non-repudiable. A third party verifies
without a shared secret. This is the encryption-based receipt path.

## Explore the lanes

```bash
flywheel lanes              # list every registered lane
flywheel lanes --probe      # live MCP handshake per lane
```

The registered lanes and their roles:

| Lane | Role |
|---|---|
| gather | Research intake + provenance receipts |
| crucible | Falsifiable verification + re-check |
| index | Workspace map + symbol graph + verified wiki |
| forum | Witnessed causal ledger + model-agnostic routing |
| learn | Accountable learning forge |
| telos | Reconciliation lane (5-tool workflow) + creative engine |
| local-model | Trained 14B proposer + verified-inference harness |
| writing | Private authoring workspace: scoped revisions + export receipts |
| relay | Accountable coding agent on any model endpoint |
| plexus | Capability discovery + auto-wiring of the tool mesh |
| mneme | Accountable memory: recall with re-derivable ranking receipts |
| calibrate-pro | Evidence-labeled display calibration (read-only over MCP) |
| accountable-surface | Witnessed perception + operator-grant execution gate |
| canon | One memory bank and personality across harnesses (read-only over MCP) |
| bulletin | Shared web board: agents post under an ed25519 identity |

`flywheel lanes` is the authority on this list; the registry decides, not this
table.

Call any lane via the generic lane caller:

```
POST /api/lane/gather/gather.run
{"args": {"query": "AI safety"}, "governance_tier": "T1"}
```

## Explore the infrastructure controls

```python
from harness.infra.egress import scan_egress
from harness.infra.credential_scanner import scan_environment
from harness.infra.isolation_test import run_isolation_test

# Scan active network connections
receipts = scan_egress(run_id="security-check")

# Scan for exposed credentials
findings = scan_environment()

# Run pre-boundary isolation test
result = run_isolation_test(run_id="pre-run-check")
print(f"isolation: {result['overall_verdict']}")  # MATCH / DRIFT / UNVERIFIABLE
```

## Explore the organizational learning loop

```python
from harness.lesson import build_lesson
from harness.lesson_store import LessonStore

store = LessonStore()
store.append_built(
    kind="intent-outcome",
    source_organ="accountable-surface",
    source_refs=[{"organ": "a", "ref": "cert", "digest": "a"*64}],
    claim="allowed action rolled back",
)
print(f"lessons: {len(store)}")
print(f"patterns: {len(store.patterns())}")
print(f"verify: {store.verify()['verdict']}")  # MATCH
```

## Read more

- [RELEASE-NOTES-1.0.0.md](RELEASE-NOTES-1.0.0.md): current published release notes
- [RELEASE-NOTES-1.0.0.md](RELEASE-NOTES-1.0.0.md): unreleased candidate scope and holds
- [docs/CONTEXT-MEMORY.md](docs/CONTEXT-MEMORY.md): context and memory owner/project binding
- [docs/native-cli-session-contract.md](docs/native-cli-session-contract.md): native CLI profile and session contract
- [docs/native-continuation.md](docs/native-continuation.md): source-bound continuation preview and limits
- [docs/writing-workspace.md](docs/writing-workspace.md): Writing Workspace custody and MCP launcher rules
- [docs/LESSON-LOOP.md](docs/LESSON-LOOP.md): the learning loop architecture
- [docs/GUIDE-LESSON-LOOP.md](docs/GUIDE-LESSON-LOOP.md): full guide and spec
- [docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md](docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md): security assessment
- [CREDO.md](CREDO.md): the belief
- [The Unbundling](https://github.com/HarperZ9/flywheel/blob/main/docs/essays/2026-07-13-the-unbundling.md): the long form

---

**Zentropy Labs** - order out of entropy. Built by Zain Dana Harper in Seattle.
