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

## Install

```bash
pip install flywheel-verify
```

(`flywheel-verify` is the PyPI distribution name; the installed command is
`flywheel`. From a source checkout: `pip install -e .`.)

Zero runtime dependencies. Python 3.11+. Stdlib only. No model download is
required: the engine works immediately against any hosted provider you hold a
key for, and local models are an optional layer (ollama needs no extras; the
published 14B/32B weights are separate downloads). Optional extras unlock the
paths that need third-party packages, and are never required:

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

Download `Flywheel-Setup-<version>-x64.exe` from the
[releases page](https://github.com/HarperZ9/flywheel/releases) and verify it
against the release's `SHA256SUMS.txt` (engine bundled, no Python needed).
From a dev checkout:

```bash
cd desktop && flutter run -d windows
```

The desktop client shows 28 views in a collapsible side rail, organized by
group: Start (World, Endpoints, Lanes), Do (Agent, Companion, Code, Train,
Studio), Know (Graph, Academy, Lessons, Governance, Receipts, Feeds,
Discourse, Projects), Advanced (Instruments, Science, Memory, Plugins,
Workflows, Compare, Uplift, Plan, Lint).

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
flywheel lanes              # list the 7 registered lanes
flywheel lanes --probe      # live MCP handshake per lane
```

| Lane | Role | Tier |
|---|---|---|
| gather | Research intake + provenance receipts | T1 |
| crucible | Falsifiable verification + re-check | T1 |
| index | Workspace map + symbol graph | T1 |
| forum | Witnessed causal ledger + routing | T1 |
| learn | Accountable learning forge | T1 |
| telos | Reconciliation lane (5-tool workflow) | T1 |
| local-model | Trained proposer + verified-inference | T2 |

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

- [docs/LESSON-LOOP.md](docs/LESSON-LOOP.md): the learning loop architecture
- [docs/GUIDE-LESSON-LOOP.md](docs/GUIDE-LESSON-LOOP.md): full guide and spec
- [docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md](docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md): security assessment
- [CREDO.md](CREDO.md): the belief
- [The Unbundling](https://github.com/HarperZ9/flywheel/blob/main/docs/essays/2026-07-13-the-unbundling.md): the long form

---

**Zentropy Labs** - order out of entropy. Built by Zain Dana Harper in Seattle.
