# Flagship demo shots

Short, honest terminal recordings of each flagship tool, captured by the
zero-dependency recorder at `scripts/demo_recorder.py`. Every shot runs a small
demo script (a JSON list of titled steps), captures the real stdout, exit code,
and wall time per step, and writes two files into `demos/<name>/`:

- `player.html` — a self-contained, offline terminal player. Open it in any
  browser to watch the shot with its narration. No network, no dependencies.
- `transcript.json` — the honest evidence (schema `harness.demo-transcript/v1`),
  including a `receipt_sha256` over the captured steps.

Every command below is read-only and fast. None of them loads a model, runs
inference, trains, or quantizes. The heaviest step is a `--help` render, a
`status`/`doctor` receipt, or a `type` of a receipt already on disk.

## Re-recording

```
python scripts/demo_recorder.py --script demos/scripts/<flagship>-showcase.json --name <flagship>-showcase
```

Recordings in this folder were made with `PYTHONUTF8=1` in the environment so
the tools emit clean UTF-8 into the captured pipe (a couple of them print a
checkmark or a dash). Setting it is optional but recommended for a clean shot.

## The shots

All nine shots below recorded **live** (every step executed for real, exit 0).
No shot needed a `--dry-run` placeholder.

| Flagship | Script | What it shows | Headline command | Mode |
| --- | --- | --- | --- | --- |
| index | `scripts/index-showcase.json` | repo maps, dependency graph, context packs | `python -m index_graph --help` then `status` | live |
| forum | `scripts/forum-showcase.json` | accountable multi-agent orchestration + ledger | `python -m forum --help` then `status` | live |
| gather | `scripts/gather-showcase.json` | accountable research intake with source receipts | `python -m gather --help` then `status` | live |
| crucible | `scripts/crucible-showcase.json` | accountable judgment: register, test, witness a verdict | `python -m crucible --help` then `status` | live |
| telos | `scripts/telos-showcase.json` | local-first MCP workbench unifying every flagship | `node demo/catalog.mjs --summary` then `doctor` + `status` | live |
| mneme | `scripts/mneme-showcase.json` | accountable agent memory + a self-contained inspector page | `python -m mneme --help` then `inspect` | live |
| relay | `scripts/relay-showcase.json` | local-first coding agent with failover + per-turn receipts | `python -m relay --help` then `--health` | live |
| plexus | `scripts/plexus-showcase.json` | interop mesh that discovers real capability edges | `python -m plexus --help` then `discover --builtin` | live |
| local-model | `scripts/local-model-showcase.json` | the flywheel harness + its release receipts | `python scripts/run_harness_cli.py --help` then two receipt reads | live |

## Notes on two commands

- **mneme** is not pip-installed in this environment yet, so its steps set
  `PYTHONPATH=./mneme/src` (and `PYTHONUTF8=1`) inline before
  `python -m mneme ...`. The command stays self-contained and runs from any
  working directory.
- **relay `--health`** is a reachability probe only. It reports which local
  tiers are up (the trained serve endpoint and the Ollama fallback) and loads
  no model. It is fast and read-only.

## The existing baseline shot

`demos/harness-first-run/` predates these and includes a final step that asks
the local 14B coder to continue a function. That one is intentionally excluded
from the read-only set here because it exercises a live model endpoint.

## Evidence demos and receipts that moved in

Five folders here are not recorded shots. Each was its own repository and now lives in this one as
its final tree, in one commit that names the source commit. They have no `transcript.json`, so
`scripts/build_demos_index.py` leaves them out of `index.json`. Their checks run in
`.github/workflows/demos.yml` when a change touches one of them.

| Demo | What it shows | Run it | Came from | Checks |
|---|---|---|---|---|
| [flywheel-evidence-task](flywheel-evidence-task/) | The evidence-task skill as a plugin at a repository root: a claim becomes a source-linked evidence packet with measurements and false-success controls. The maintained plugin is `plugins/flywheel-evidence-task`. | `python scripts/check_plugin.py` | `HarperZ9/flywheel-evidence-task` at `7daa67ba` | plugin consistency with a corrupted-copy control, art receipts |
| [flywheel-receipt-demo](flywheel-receipt-demo/) | The receipt path in one command: an honest receipt re-derives as MATCH and a forged one as DRIFT. Pinned to `flywheel-verify==1.0.0`. | `python demo/run_demo.py` | `HarperZ9/flywheel-receipt-demo` at `b2cb71bf` | the demo run, art receipts |
| [bootloops-second-checker](bootloops-second-checker/) | An independent second checker for BootLoops RECEIPT v1.0 witnesses, with a Lean 4 kernel check over ZMod p and sealed run folders. | `python -m pytest -q tests` | `HarperZ9/bootloops-second-checker` at `f29a7201` | pytest on Linux and Windows, sealed bytes, run-folder manifests |
| [crewai-kickoff-replay-receipt](crewai-kickoff-replay-receipt/) | A sealed replay audit of CrewAI `kickoff_for_each` with red and green logs and a candidate patch. | `python verify_public.py` | `HarperZ9/crewai-kickoff-replay-receipt` at `f9a2192b` | its verifier, `SHA256SUMS` |
| [vllm-ci-forum-receipt](vllm-ci-forum-receipt/) | A sealed, read-only Forum receipt over public vLLM CI data, with pinned snapshots and stated unknowns. | `python verify_publication.py` | `HarperZ9/vllm-ci-forum-receipt` at `565dc98d` | its verifier, `SHA256SUMS.txt`, its 27 unit tests, Forum ledger verify |

The two sealed receipts are byte-for-byte copies. Their own repositories stay the published record:
`packages/seal-watch` clones each one fresh every day and runs its verifier.
