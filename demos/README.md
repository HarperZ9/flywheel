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
  `PYTHONPATH=C:\dev\public\mneme\src` (and `PYTHONUTF8=1`) inline before
  `python -m mneme ...`. The command stays self-contained and runs from any
  working directory.
- **relay `--health`** is a reachability probe only. It reports which local
  tiers are up (the trained serve endpoint and the Ollama fallback) and loads
  no model. It is fast and read-only.

## The existing baseline shot

`demos/harness-first-run/` predates these and includes a final step that asks
the local 14B coder to continue a function. That one is intentionally excluded
from the read-only set here because it exercises a live model endpoint.
