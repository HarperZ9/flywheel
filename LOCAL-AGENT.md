# The Local Agent (offline / exhaustion tier)

A standalone agent that keeps you working when the subscription or a hosted API
is out of usage. It runs entirely on models on this machine and proxies no
hosted account.

## What it is

`harness/local_agent.py` + `harness/local_agent_cli.py`. Two local backends,
health-probed, with automatic failover in preference order:

1. **serve** — the trained 14B/32B behind `harness/serve.py` (`/generate`).
2. **ollama** — a local Ollama model (`/api/chat`), auto-selecting the largest
   pulled model (32b > 14b > 7b), so pulling the 14B/32B into Ollama upgrades
   the backend with no code change.

Every turn is wrapped through `messages_api`, so even the fallback tier emits a
re-checkable per-turn receipt (request + prompt + model + response).

## Use

```
# which local tiers are live right now?
python -m harness.local_agent_cli --health

# one-shot, with file context
python -m harness.local_agent_cli "explain this function" --file harness/loop.py

# interactive REPL (/health, /reset, /exit)
python -m harness.local_agent_cli

# force a backend or an Ollama model
python -m harness.local_agent_cli "hi" --backend ollama --model qwen2.5:7b
```

Exit code of `--health` is `0` when at least one tier is live, `1` otherwise, so
a launcher can gate on it.

## Bringing the trained models online

The `serve` tier is preferred but only live when `serve.py` is running against a
present checkpoint:

```
# 14B (default path in serve.py; repoint with SERVE_MODEL_PATH)
python harness/serve.py         # serves Qwen2.5-Coder-14B-Instruct (nf4)

# 32B: fetch first (scripts/download_32b.sh), then
SERVE_MODEL_PATH=/path/to/Qwen2.5-Coder-32B-Instruct python harness/serve.py
```

Until then the agent falls over to Ollama automatically. On this box that is
`qwen2.5:7b` today; `ollama pull qwen2.5-coder:14b` (or 32b) makes the stronger
model the default local backend.

## Agentic mode (gated tools + a witnessed trajectory)

`--agent` turns a prompt into a task the local model works with tools:
`repo_map` (a compact code outline so the model finds the right file), `read_file`
/ `list_dir` (sandboxed to `--root`), `edit_file` (precise search/replace where
the `old` text must match exactly once, so an ambiguous edit is refused not
guessed), plus `write_file` / `run` behind `--allow-write` / `--allow-exec` (a
denylist still blocks destructive commands). The whole run (turns, tool calls,
tool results) is appended to a hash-chained session ledger you can save and
re-verify.

```
# read-only investigation (safe by default: no writes, no exec)
python -m harness.local_agent_cli --agent "read note.txt and tell me the secret word" \
    --root /path/to/dir --save run.jsonl

# allow edits + running the tests it writes
python -m harness.local_agent_cli --agent "add a failing test for foo() then make it pass" \
    --root . --allow-write --allow-exec --max-steps 8 --save run.jsonl
```

Every run prints `verified=<bool>` and a `checkpoint` (the ledger head hash). A
saved `run.jsonl` is tamper-evident: reload it with `SessionLedger.load(path)`
and `.verify()` re-derives the chain.

## Where it stands vs the class

| Capability | aider | gptme | open-interpreter | ollama run | **local-agent** |
|---|---|---|---|---|---|
| Runs on local Ollama / trained model | ~ | yes | yes | yes | **yes (auto-failover)** |
| Agentic tool loop (files + shell) | edits | yes | yes | no | **yes (gated)** |
| Precise search/replace edits | yes | ~ | ~ | no | **yes (unique-match)** |
| Repo map / code navigation | yes | no | no | no | **yes (ast + regex)** |
| Multi-language symbols | tree-sitter | no | no | no | **regex (py=ast)** |
| Git auto-commit | yes | no | no | no | **yes** |
| Token streaming | yes | yes | yes | yes | **yes (ollama)** |
| Default-deny write/exec + denylist | no | no | no | n/a | **yes** |
| Session save / resume | ~ | yes | ~ | no | **yes** |
| **Hash-chained, re-verifiable trajectory** | no | no | no | no | **yes** |
| **Commit message bound to that trajectory** | no | no | no | no | **yes** |
| Per-turn content-addressed receipt | no | no | no | no | **yes** |

The first rows are table stakes the class already meets; the bold rows are the
ones nobody else in the class has. That is the wedge: a local agent whose run is
provable, not just logged, with the git history pointing back at the proof.

Honest remaining gaps vs aider: its multi-language parsing is tree-sitter (exact)
where ours is regex (crude, Python stays ast-exact); aider supports a wide range
of hosted models and has a larger ecosystem. The local agent's edge is running
offline with a witnessed, git-anchored trajectory.

```
# stream a one-shot answer
python -m harness.local_agent_cli "explain async in one paragraph" --stream

# agentic edit that auto-commits (existing repo only; never inits, never pushes)
python -m harness.local_agent_cli --agent "fix the off-by-one in paginate()" \
    --root . --allow-write --allow-exec --auto-commit
```

## Online endpoints (reach every provider)

`--online` extends the ladder past local models to **codex / claude / gemini /
deepseek**, each in whatever access mode you have credentials for, with automatic
failover. Legitimate by construction: keys from the environment, subscriptions
from the official CLI's own auth, gateways from a configured base URL. Nothing is
forged, harvested, or metered around; a missing credential just drops that tier.

| Mode | How it is reached |
|---|---|
| `plan` / `max` | the official CLI (`claude`, `codex`) using your subscription auth |
| `api` | the provider's public API + `<PROVIDER>_API_KEY` |
| `provider` | a gateway (OpenRouter, ...) via `<PROVIDER>_PROVIDER_BASE_URL` |
| `cloud` | a cloud OpenAI-compatible endpoint via `<PROVIDER>_CLOUD_BASE_URL` + `_CLOUD_KEY` |

```
python -m harness.local_agent_cli --health --online          # which tiers are live?
python -m harness.local_agent_cli "review this" --online --file x.py
python -m harness.local_agent_cli --agent "fix the bug" --root . --allow-write --online
```

The failover order runs local first (free, private), then your subscriptions,
then api/provider/cloud, so you only spend metered tokens when the free tiers are
exhausted. Model per provider is overridable via `<PROVIDER>_MODEL`.

## MCP server (the agent as a tool)

`--mcp` runs a zero-dep stdio MCP server exposing `local_agent_health`,
`local_agent_chat`, and `local_agent_run` (gated agentic task with a witnessed
ledger). Point any MCP client (Claude Code included) at it to use this agent as a
fallback tier:

```
python -m harness.local_agent_cli --mcp
```

## Boundaries

- Credentials come only from the environment (API keys), the official CLI's own
  auth (subscriptions), or a base URL you configure (gateways). Nothing is
  forged, no cover identity is minted, no session token is harvested, and no
  billing is evaded. A missing credential means the tier is simply absent.
- Subscriptions are reached by invoking the operator's own authenticated CLI
  (`claude`, `codex`), never by proxying or replaying its OAuth token to another
  client.

## Modules

- `harness/local_agent.py` — backends + failover + per-turn receipts.
- `harness/local_tools.py` — the gated tool surface (repo_map/read/list/edit/write/run;
  sandbox, default-deny, denylist, unique-match edits).
- `harness/local_repomap.py` — the ast-based code map for navigation.
- `harness/local_session.py` — the hash-chained, resumable session ledger.
- `harness/local_loop.py` — the agentic loop tying them together.
- `harness/local_agent_cli.py` — CLI / REPL / `--agent`.

## Tests

- `tests/test_local_agent.py` — 9 falsifiers: backend preference, failover on
  down and on mid-turn error, loud failure when nothing is healthy,
  receipt-changes-with-response, typed errors, strongest-model preference.
- `tests/test_local_agentic.py` — 14 falsifiers: tool sandboxing, write/exec
  gate + denylist, unique-match edit_file, repo_map, unknown-tool / exception
  safety, ledger chaining + tamper detection + save/load, the loop executing
  gated tools and witnessing the full trajectory, max-steps termination.
- `tests/test_local_repomap.py` — 5 falsifiers: symbol extraction with lines,
  ignore dirs, non-Python listing, truncation reporting, unparseable-file safety.

All hermetic (injected transport / scripted agent; no network, no GPU). 28 total.
