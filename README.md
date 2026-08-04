# Flywheel

> One platform: routing, verification, the lane layer, the closed loop, and the
> projected world. The native desktop surface for accountable AI infrastructure.

Flywheel is the engine and native client for a verified-inference loop: a model
perceives only through witnessed organs, acts only through a gate it cannot
talk past, journals everything, and verifies its own work by re-perceiving.

The flagship tools (gather, crucible, index, forum, learn, telos) are lanes
inside Flywheel, each a provisioned, health-checked organ reachable through one
surface. Every agent tool call carries a sealed, chain-linked receipt a third
party re-verifies offline.

**Proof before trust.**

## What is in this repo

This is a monorepo containing both halves of the platform:

- **`harness/`** is the Python engine: the gateway (localhost HTTP API), the
  agent loop, the receipt discipline, the lane layer, the verified-inference
  loop, the tool-call receipt system. Zero runtime dependencies (stdlib only).
- **`desktop/`** is the Flutter native client: 24 views, 50 widgets, zero
  webview embedding. Talks to the gateway over localhost. Launches a bundled
  frozen engine by absolute path on a clean machine (no Python, no PATH, no
  network).
- **`site/`** is a dev/CI fallback browser shell (not the primary UI).

## Run it now

Start the gateway (the engine keeps the loop, receipts, lanes, and routing):

```
flywheel app --port 8799
```

The **native surface is Flywheel Desktop**. From a dev checkout:

```
cd desktop
flutter run -d windows --release
```

The gateway also serves a `/site/index.html` shell as a dev/CI fallback.

## The lane model

Flywheel encompasses the tool family. Each flagship is a lane:

| Lane | Repo | Role |
| --- | --- | --- |
| gather | [gather](https://github.com/HarperZ9/gather) | Research intake + provenance receipts |
| crucible | [crucible](https://github.com/HarperZ9/crucible) | Falsifiable verification (MATCH / DRIFT / UNVERIFIABLE) |
| index | [index](https://github.com/HarperZ9/index) | Workspace map + symbol graph + context envelopes |
| forum | [forum](https://github.com/HarperZ9/forum) | Witnessed causal ledger + model-agnostic routing |
| learn | [learn](https://github.com/HarperZ9/learn) | Accountable learning forge |
| telos | [telos](https://github.com/HarperZ9/telos) | The reconciliation lane |

Check their health through one surface:

```
flywheel lanes
flywheel lanes --probe    # live MCP handshake per lane
```

## The receipt discipline

Every agent tool invocation carries a sealed receipt binding:

- **what the tool was** (capability class: read / write / exec / external-mcp)
- **what it was allowed to do** (admission decision from the gate)
- **what it actually did** (witnessed args + output sha256 digests, never raw content)
- **whether a stranger can re-walk it** (offline-verifiable, chain-linked)

Receipts compose into a transitive-witness DAG where a drifted action degrades
exactly its downstream dependents. The five flagships emit organ-bundle entries
on a shared proof-surface spine so cross-tool receipts compose end-to-end.

## The organizational learning loop

The layer above audit. The receipt discipline records what happened at machine
resolution. The learning loop feeds forward: it derives lessons from witnessed
divergences (an allowed action that rolled back, a memory whose source drifted,
a graded failure), stores them in a durable, hash-chained, append-only memory,
and surfaces recurring patterns as improvement candidates for human admission.
A lesson is not a note an operator wrote; it is a claim bound by hash to its
evidence, re-checkable offline, fail-closed when the evidence is gone. See
[docs/LESSON-LOOP.md](docs/LESSON-LOOP.md).

## Offline-first

The Flutter desktop GUI launches a bundled engine by absolute path and serves
its UI menu on localhost only. No external web address is contacted to show the
GUI. The gateway serves `/api/*` and the UI on `http://127.0.0.1:8799`.

## Install

```
pip install flywheel-verify
flywheel up
```

`flywheel-verify` is the PyPI distribution name (the bare `flywheel` name is an
unrelated package); the installed command is `flywheel`. Zero runtime
dependencies, stdlib only.

**No model download required.** The engine is ready for real work the moment
it installs: point it at any hosted provider you hold a key for (the roster
reports credential presence only, never values) and every route carries the
same receipt discipline. Local models get the same support and stay optional: ollama
needs no extras at all (the gateway talks to it over HTTP), the published
[14B](https://huggingface.co/zaindanaharper/flywheel-local-coder-14b) and
[32B](https://huggingface.co/zaindanaharper/flywheel-local-coder-32b) weights
are separate downloads for when you want them, and the local HF
serve/training stack installs with `pip install "flywheel-verify[local]"`.
Receipt signing and egress monitoring have their own extras (`[signing]`,
`[monitor]`); receipt verification stays stdlib-only.

Or from source:

```
git clone https://github.com/HarperZ9/flywheel.git
cd flywheel
pip install -e .
python scripts/run_harness_cli.py app --port 8799
```

The native desktop app ships as a Windows installer with the engine bundled
(no Python needed): download `Flywheel-Setup-<version>-x64.exe` from the
[releases page](https://github.com/HarperZ9/flywheel/releases) and verify it
against the release's `SHA256SUMS.txt`.

## Documentation

- [QUICKSTART.md](QUICKSTART.md): first ten minutes
- [WALKTHROUGH.md](WALKTHROUGH.md): guided tour
- [docs/LESSON-LOOP.md](docs/LESSON-LOOP.md): the organizational learning loop (architecture)
- [docs/GUIDE-LESSON-LOOP.md](docs/GUIDE-LESSON-LOOP.md): the organizational learning loop (full guide and spec)
- [docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md](docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md): Flywheel against the July 2026 agentic security convergence
- [CREDO.md](CREDO.md): the belief

## License

FSL-1.1-MIT (Functional Source License). See [LICENSE](LICENSE).
