<p align="center"><img src="docs/art/flywheel-header.svg" alt="Flywheel: run an AI task with any model, keep a record you can recheck offline." width="100%"></p>

**Run an AI task with any model. Keep a record you can recheck offline.**

[![PyPI](https://img.shields.io/pypi/v/flywheel-verify?style=flat-square&labelColor=14041b&color=f8cc43)](https://pypi.org/project/flywheel-verify/)
[![license](https://img.shields.io/badge/license-FSL--1.1--MIT-8f8095?style=flat-square&labelColor=14041b)](LICENSE)
[![CI](https://github.com/HarperZ9/flywheel/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/flywheel/actions/workflows/ci.yml)
[![downloads](https://img.shields.io/pypi/dm/flywheel-verify?label=downloads&style=flat-square&labelColor=14041b)](https://pypi.org/project/flywheel-verify/)
![python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square&labelColor=14041b)
![deps: none (core)](https://img.shields.io/badge/core%20deps-none-success?style=flat-square&labelColor=14041b)

Flywheel runs an AI task with the local or hosted model and tools you choose. It
records the run, and optional sealed tool-call receipts can be inspected and
rechecked offline. The repository also includes a native desktop app.

Flywheel has two parts. The Python engine routes tasks, checks tool requests,
runs verification, writes the run ledger, and serves a local gateway. The
Flutter client provides the native desktop interface.

[Project Telos](https://harperz9.github.io) | [gather](https://github.com/HarperZ9/gather) | [crucible](https://github.com/HarperZ9/crucible) | [index](https://github.com/HarperZ9/index) | [forum](https://github.com/HarperZ9/forum) | [telos](https://github.com/HarperZ9/telos) | [learn](https://github.com/HarperZ9/learn) | [relay](https://github.com/HarperZ9/relay) | [mneme](https://github.com/HarperZ9/mneme)

## Try it

```powershell
python -m pip install flywheel-verify
flywheel app --port 8799
```

This starts the local API gateway on `http://127.0.0.1:8799`.

## How a run works

One task, from the moment you send it to the point where somebody who was not
there can check it. Every stage writes a receipt, and the last stage needs no
network and no model.

<p align="center"><img src="docs/art/run-lifecycle.svg" alt="Eight stages: a task is routed to a model, the model asks for a tool, the capability check either allows it or refuses it with the reason returned to the model, the tool runs, a receipt is written, the ledger is sealed, and a later recheck reports match, changed, or unverifiable." width="100%"></p>

The refusal edge is the one worth reading twice. A blocked tool request is not
an error the run dies on: the reason goes back to the model, which can pick a
different route. What the ledger keeps is the request, the refusal, and the
reason, so a reader later can see what was asked for as well as what ran.

## What the capability check decides

Stage four reads a shell command the way a shell reads it, then names what
the command is able to do. That name settles the decision. Seven commands
are below with the reason each one lands where it does.

<p align="center"><img src="docs/art/what-runs.svg" alt="Seven shell commands and what the capability check does with each of them. A dangerous word inside quotes is a printed string and runs, while the same word reached through a command substitution is found and blocked. A pipe records both of its capability classes even though one of them names the decision. An environment prefix does not hide the executable behind it. A command that will not parse is escalated to a person rather than admitted. The marked row is the honest gap: an executable the curated map has never seen is admitted, and written down as unknown." width="100%"></p>

A denied word matters only in the executable position, so quoted text
prints and a substitution gets walked into. The marked row is the gap this
repository does not paper over: the map of names is curated by hand, and an
executable it has never seen is admitted, then written down as unknown.

## Verification record

The review for [pull request #60](https://github.com/HarperZ9/flywheel/pull/60)
records the checks for this README change:

- The file-size, standard-library verifier, claim-language, public-instruction,
  and writing gates passed.
- `python -m harness.cli_entry gate` returned `PASS` and an offline recheck of
  `MATCH`.
- GitHub Actions ran the whole test suite on Ubuntu and Windows. The linked CI
  checks are the source of record; this README does not freeze a test count
  that can change by revision or platform.

These checks cover the repository's deterministic code and documentation
paths. They do not prove that a model answer is correct, measure live provider
reliability, or test every host and hardware configuration.

## What is in this repo

<p align="center"><img src="docs/schematics/architecture.svg" alt="The browser shell, the command line, curl and MCP clients all reach one gateway on localhost, which routes to a local model or an external check and writes a receipt either way, escalating only what does not pass." width="100%"></p>

This monorepo contains both halves of the platform:

- **`harness/`** is the Python engine. It runs tasks, checks tool requests,
  writes receipts, discovers companion tools, and exposes the localhost API.
  The installed runtime uses only the Python standard library.
- **`desktop/`** is the Flutter client. It talks to the gateway over localhost
  and can launch the bundled engine on a Windows machine without a separate
  Python installation.
- **`site/`** is the browser fallback used in development and CI.

To run the native client from a development checkout:

```
cd desktop
flutter run -d windows --release
```

From a repository checkout, `python -m harness.cli_entry app --port 8799` also
serves the development and CI fallback at `/site/index.html`.

## Included tools

Flywheel can connect to twelve companion tools. Each has a public repository:

| Tool | Repository | What it does |
| --- | --- | --- |
| gather | [gather](https://github.com/HarperZ9/gather) | Collect research and record its sources. |
| crucible | [crucible](https://github.com/HarperZ9/crucible) | Recheck a claim and report a match, change, or missing evidence. |
| index | [index](https://github.com/HarperZ9/index) | Map files and symbols in a workspace. |
| forum | [forum](https://github.com/HarperZ9/forum) | Route work among models and record decisions. |
| learn | [learn](https://github.com/HarperZ9/learn) | Turn your material and recorded attempts into a study plan. |
| telos | [telos](https://github.com/HarperZ9/telos) | Reconcile findings from several tools. |
| local-model | [archived predecessor](https://github.com/HarperZ9/local-model) | Historical engine repository. Its runtime is now part of Flywheel; the lane name remains for compatibility. |
| relay | [relay](https://github.com/HarperZ9/relay) | Run a coding agent with a local or hosted model. |
| plexus | [plexus](https://github.com/HarperZ9/plexus) | Find installed tools and connect them. |
| mneme | [mneme](https://github.com/HarperZ9/mneme) | Store and retrieve memories with source checks. |
| calibrate-pro | [calibrate-pro](https://github.com/HarperZ9/calibrate-pro) | Check display calibration targets and readiness. |
| accountable-surface | [accountable-surface](https://github.com/HarperZ9/accountable-surface) | Require approval before actions and keep a tamper-evident record. |

List their configured state or probe their live MCP connections:

```
flywheel lanes
flywheel lanes --probe    # live MCP handshake per lane
```

## Run records and sealed receipts

<p align="center"><img src="docs/schematics/verified-loop.svg" alt="A local model proposes, an external check disposes, and the pair is written to a content-addressed receipt; a pass goes to the proof cache and anything that does not pass escalates." width="100%"></p>

Routed runs keep a ledger containing tool names, arguments, and outputs. When
sealed tool-call receipts are enabled, they also record:

- the capability (`builtin-read`, `builtin-write`, `builtin-exec`,
  `external-mcp`, or `unknown`);
- the outcome;
- argument and output hashes;
- the prior receipt's hash for offline verification.

Optional sealed receipts form an ordered hash chain. If one receipt is invalid,
later entries in that chain become unverifiable.

## Checking an answer before it ships

An assistant that rechecks its own arithmetic gets the same wrong number twice.
So Flywheel checks a value against the source that decides it, and reports three
outcomes rather than two: the value agrees and the answer names its source, the
value disagrees, or nothing could confirm it.

```
flywheel check-output --contract task.contract.json --answer answer.json --allow-commands
```

Exit 0 confirmed, exit 1 disagrees, exit 3 unchecked. An unchecked value never
reads as a confirmed one. See
[docs/OUTPUT-VALIDATION.md](docs/OUTPUT-VALIDATION.md) for the contract format,
the checker protocol, and the retry loop.

## Lessons from recorded failures

A proposed lesson includes hashes of its evidence and remains a proposal until
a person accepts it. Verification detects changes to the lesson's sealed claim
and evidence hashes. The originating system must separately recheck whether
referenced evidence still exists or has changed. See
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

Subscription sign-in is wired in: `flywheel auth login <provider>` runs a
stepwise flow (documented PKCE where the provider sanctions it, the
provider's own official tool where it does not), stores the token in the OS
credential store, and the router picks it up with no further setup. See
[GETTING-STARTED.md](GETTING-STARTED.md).

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
- [GETTING-STARTED.md](GETTING-STARTED.md): install, sign in, first run
- [WALKTHROUGH.md](WALKTHROUGH.md): guided tour
- [docs/REMOTE-ACCESS.md](docs/REMOTE-ACCESS.md): drive the same loop from your phone
- [docs/LESSON-LOOP.md](docs/LESSON-LOOP.md): the organizational learning loop (architecture)
- [docs/GUIDE-LESSON-LOOP.md](docs/GUIDE-LESSON-LOOP.md): the organizational learning loop (full guide and spec)
- [docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md](docs/ASSESSMENT-AGENTIC-SECURITY-2026-08.md): Flywheel against the July 2026 agentic security convergence
- [docs/OUTPUT-VALIDATION.md](docs/OUTPUT-VALIDATION.md): check an answer against the source that decides it
- [CREDO.md](CREDO.md): the belief

## Development disclosure

Zain Dana Harper maintains this repository. AI-assisted tools are used for
parts of development and documentation. Public source, tests, benchmark
artifacts, and releases are the evidence for what ships; AI output is not
treated as proof.

## License

FSL-1.1-MIT (Functional Source License). See [LICENSE](LICENSE).
