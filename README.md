# Flywheel

Flywheel runs an AI task with the local or hosted model and tools you choose. It
records the run, and optional sealed tool-call receipts can be inspected and
rechecked offline. The repository also includes a native desktop app.

Flywheel has two parts. The Python engine routes tasks, checks tool requests,
runs verification, writes the run ledger, and serves a local gateway. The
Flutter client provides the native desktop interface.

## Try it

```powershell
python -m pip install flywheel-verify
flywheel app --port 8799
```

This starts the local API gateway on `http://127.0.0.1:8799`.

## Verification record for `b5b35f5`

Verified on 2026-08-31 against commit
[`b5b35f5`](https://github.com/HarperZ9/flywheel/commit/b5b35f528d1b3bef83abc4dfd8412bd808c664fe):

- The file-size, standard-library verifier, claim-language, public-instruction,
  and writing gates passed.
- `python -m harness.cli_entry gate` returned `PASS` and an offline recheck of
  `MATCH`.
- `python -m pytest tests/ -q` exited successfully. Pytest collected 5,683
  tests; all executed tests passed, with platform-conditional cases skipped.

These checks cover the repository's deterministic code and documentation
paths. They do not prove that a model answer is correct, measure live provider
reliability, or test every host and hardware configuration.

## What is in this repo

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
| local-model | [local-model](https://github.com/HarperZ9/local-model) | Run local models through Flywheel's task and verification engine. |
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

Routed runs keep a ledger containing tool names, arguments, and outputs. When
sealed tool-call receipts are enabled, they also record:

- the capability (`builtin-read`, `builtin-write`, `builtin-exec`,
  `external-mcp`, or `unknown`);
- the outcome;
- argument and output hashes;
- the prior receipt's hash for offline verification.

Optional sealed receipts form an ordered hash chain. If one receipt is invalid,
later entries in that chain become unverifiable.

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
- [CREDO.md](CREDO.md): the belief

## Development disclosure

Zain Dana Harper maintains this repository. AI-assisted tools are used for
parts of development and documentation. Public source, tests, benchmark
artifacts, and releases are the evidence for what ships; AI output is not
treated as proof.

## License

FSL-1.1-MIT (Functional Source License). See [LICENSE](LICENSE).
