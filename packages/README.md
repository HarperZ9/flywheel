# Packages

Tools that live in this repository and install on their own. Each folder keeps its own
`pyproject.toml` or `package.json`, its own licence file and its own tests. None of them is part of
the `flywheel-verify` wheel or sdist.

Install one from a checkout:

```
python -m pip install ./packages/proof-surface
```

Tests run in `.github/workflows/packages.yml` when a change touches `packages/`.

| Package | What it does | Entry points | Came from | Tests |
|---|---|---|---|---|
| [service-desk-incident-env](service-desk-incident-env/) | A runnable incident-management environment for testing agent workflows. | see its README | this repository | main suite |
| [proof-surface](proof-surface/) | Checks an agent's trace against the permissions it was granted and writes JSON packets with a verdict and a report. | `telos-proof`, `proof-surface-agent-action`, `proof-surface-visual-measurement`, `proof-surface-research-claim`, `proof-surface-model-eval`, `proof-surface-optimization` | `HarperZ9/proof-surface` at `6f02ca9c` | pytest, public surface check, bundle verify |
| [proof-surface-report](proof-surface-report/) | Renders proof-surface packets and receipts into Markdown for a reviewer. | `proof-surface-report` | `HarperZ9/proof-surface-report` at `eaea1f6e` | pytest |
| [repo-proof-index](repo-proof-index/) | Indexes proof packets, receipts and contracts into summaries. | `repo-proof-index` | `HarperZ9/repo-proof-index` at `882c6aeb` | pytest, conformance and research scoring scripts |
| [model-provenance-validator](model-provenance-validator/) | Validates model and release claims against small provenance envelopes, with redacted output. | `model-provenance-validator` | `HarperZ9/model-provenance-validator` at `64913713` | pytest, CLI on the example envelope |
| [context-curator-lite](context-curator-lite/) | Builds small context bundles with redaction, source references and hashes. | `context-curator-lite` | `HarperZ9/context-curator-lite` at `8025020a` | pytest |
| [workflow-harness-lite](workflow-harness-lite/) | Runs bounded local command workflows in parallel and writes a report or a receipt. Node. | `workflow-harness-lite` (npm bin) | `HarperZ9/workflow-harness-lite` at `f2463133` | `npm test`, `npm pack --dry-run` |
| [secret-redact-io](secret-redact-io/) | Python IO helpers that redact file, fetch, write and subprocess output and emit hash-only receipts. | `secret-redact-io` | `HarperZ9/secret-redact-io` at `565ff5b3` | pytest, public surface check |
| [agent-hook-pack](agent-hook-pack/) | Installs hooks for secret checks, branch guards, env sync and repo hygiene. | `agent-hook-pack` | `HarperZ9/agent-hook-pack` at `cdebedff` | pytest |
| [agent-routing-kit](agent-routing-kit/) | Routes agent tasks by capability, risk and context budget before files load. | `agent-route` | `HarperZ9/agent-routing-kit` at `f125e47a` | pytest |
| [public-surface-sweeper](public-surface-sweeper/) | Checks a public repo for required files, text hygiene, secret-shaped values and proof packets. | `public-surface-sweeper` | `HarperZ9/public-surface-sweeper` at `57678c63` | pytest, CLI on the clean example |
| [discover](discover/) | Checks before a release that people can find a project: README opening, topics, keywords, CITATION.cff and more. Also a GitHub Action. | `discover`, `action.yml` | `HarperZ9/discover` at `98138514` | unittest, video manifest gate |
| [accountable-engine](accountable-engine/) | Templates and a critic script that tie work to claims, receipts and a decision log. PowerShell. | `critic.ps1` | `HarperZ9/accountable-engine` at `e90429f4` | critic script runs on Windows |
| [coherence-membrane](coherence-membrane/) | Gives an agent inspectable observations of files, images and screens, each with a receipt. | `python -m coherence_membrane` | `HarperZ9/coherence-membrane` at `bcf93e1f` | pytest under xvfb, selftest, Python and JS conformance |
| [behavior-transform.io](behavior-transform.io/) | The IO boundary for read, write, exec, fetch, input and model calls, with receipts. | `behavior-transform`, `behavior-transform-io`, `bt`, `bt-validate`, `bt-doctor`, `bt-transform`, `bt-adaptive`, `bt-infer`, `bt-analyze`, `bt-recover`, `bt-intel`, `bt-trends`, `bt-enforce` | `HarperZ9/behavior-transform.io` at `70cad673` | pytest (911 tests), repo facts, doctor |
| [terminal-state-fixtures](terminal-state-fixtures/) | Evaluation environments that score an agent by the state it leaves. Three environments, each with its own pyproject. | environments under `environments/` | `HarperZ9/terminal-state-fixtures` at `71bc42de` | mlflow environment tests, METR TaskFamily tests, repo facts |
| [seal-watch](seal-watch/) | Clones two sealed evidence repos fresh every day, runs each one's verifier and a tamper self-test. | `python watch.py check|tamper|report` | `HarperZ9/seal-watch` at `3c5cfed2` | `.github/workflows/seal-watch.yml`, daily |
| [chorus](chorus/) | Reads a comment section: ranked themes, strength of feeling, split topics, and a receipt anyone can re-run. Distribution name `chorus-discourse`. | `chorus` (`run`, `corpora`, `watch`, `daemon`, `digests`, `decision`, `mcp`) | `HarperZ9/chorus` at `baa3ebf1` | pytest, repo art check |
| [learn](learn/) | A tutor that plans study, checks proof lessons, tracks mastery and misconceptions, and writes a receipt for each step. Node, npm name `@harperz9/learn`. | `learn`, `learn-mcp` (npm bins) | `HarperZ9/learn` at `ab5a7657` | `node --test` (419 tests), doctor, status, tarball smoke test |
| [plexus](plexus/) | Discovers the tools installed on a machine, plans a route across them and checks the wiring. Distribution name `plexus-mesh`. | `plexus` (`discover`, `wiring`, `validate`, `plan`, `route`, `pick`, `verify`, `graph`, `run`, `export`, `mcp`) | `HarperZ9/plexus` at `60e10120` | pytest, example tour |
| [mneme](mneme/) | Agent memory with provenance: remember, recall, forget and audit, each with a receipt that re-checks. Distribution name `flywheel-mneme`. | `mneme` (`remember`, `recall`, `drift`, `provenance`, `forget`, `scrub`, `status`, `doctor`, `mcp` and more) | `HarperZ9/mneme` at `fc7970cc` | pytest, example tour |
| [relay](relay/) | A coding agent that runs on local and hosted model endpoints with failover and a receipt for each turn. Distribution name `flywheel-relay`. | `relay` | `HarperZ9/relay` at `945d4241` | pytest, release metadata check |

Each import is the final tree of the source repository in one commit. The commit message names
the source commit. Releases published before the move stay on PyPI and on the source repository's
release page.
