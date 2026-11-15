<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/relay/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/relay/main/docs/art/hero-light.svg" alt="relay: Accountable coding agent that runs on any model endpoint. Bundles of fine lines carry the work through 4 stations, route, agent, failover and certify, along a sweeping path into a bright core." width="100%">
</picture>

# relay

Relay is a command-line coding agent that runs on the model you pick. That can
be a local model through Ollama, your Claude or Codex subscription CLI, or a
provider API key. Relay tries them in a fixed order and moves to the next one
when a model errors or runs out of quota. Each run is saved as a hash-chained
log that you can replay, view and check offline later. Pass `--check "pytest -q"`
and the run counts as done only when your own test command passes.

It suits developers who want an agent that keeps working offline on local
models, who want to see exactly what an agent changed and re-check it later, or
who want to run an agent in CI and fail the job when the tests fail. It needs
Python 3.11 or newer and has no runtime dependencies.

```
python -m pip install flywheel-relay
```

[![version: 0.7.0](https://img.shields.io/badge/version-0.7.0-e6e1d6?style=flat-square&labelColor=1a1712)](https://pypi.org/project/flywheel-relay/)
[![CI](https://github.com/HarperZ9/relay/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/relay/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-FSL--1.1--MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/relay/blob/main/LICENSE)
![python 3.11+](https://img.shields.io/badge/python-3.11%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Relay publishes to PyPI as `flywheel-relay`, with PEP 740 attestations recording
which workflow built the bytes. The installed command is `relay`. The bare name
`relay-agent` belongs to an unrelated project, and so does `relay`, so install
`flywheel-relay`.

If you would rather verify the bytes yourself than trust the index, the
hash-verified path still works and is still supported: a pinned HarperZ9 GitHub
commit or a GitHub Release wheel, where a missing checksum entry or a hash
mismatch stops before `pip install`. See
[`docs/GITHUB-ONLY-INSTALL.md`](docs/GITHUB-ONLY-INSTALL.md).

## Quickstart

Run on Windows 11 with Python 3.12, `flywheel-relay` 0.7.0 from PyPI in a fresh
virtual environment, and Ollama running locally. The outputs below are trimmed
copies of what those commands printed.

1. **Check the tool permissions, no model needed.** The probe feeds six
   prompt-injection scenarios through the agent's tool layer, assuming the model
   was fooled, and reports how many were blocked. Exit code 0 means all of them.

   ```text
   $ relay --probe-injection
     "contained": 6,
     "total": 6,
   ```

2. **See which local models answer.** Without `--online`, relay only looks on
   this machine: a local server at `127.0.0.1:8765`, then Ollama.

   ```text
   $ relay --health
     "any_live": true,
         "backend": "serve",
         "healthy": false,
         "backend": "ollama",
         "healthy": true,
         "detail": "flywheel-local-coder-32b:latest"
   ```

3. **Fix a bug, accepted only if the test passes.** A `pager.py` with an
   off-by-one slice and a `test_pager.py` that asserts on it, in a git repo:

   ```text
   $ relay --agent "fix the off-by-one in paginate() in pager.py" --root . --allow-write \
           --check "python test_pager.py" --model qwen3-coder:30b --save run.jsonl --cert run.rvc
   [agent | 3 step(s) | 13 ledger entries | verified=True | accepted=True | check=pass | ...]

   $ git diff
   -    end = start + size - 1
   +    end = start + size
   ```

   With `qwen3-coder:30b` on a 24 GB GPU this took about five minutes. The same
   task on `qwen3:8b` stopped after a cut-off tool call: the check failed,
   relay printed `accepted=False` and exited 1, and nothing was committed.
   Small local models drive the tool loop unreliably, so expect retries or use
   a larger model.

4. **Check the saved run later.** The certificate verifies offline with no model
   and no re-run. Changing one byte in the saved log breaks the chain.

   ```text
   $ relay --verify-cert run.rvc
   ALLOW  run accepted: chain intact, receipts re-derive, contract satisfied

   $ relay --view tampered.jsonl --no-color
   REFUTED  hash chain broken at seq 0 (entry_hash does not re-derive from its fields)
   ```

To use hosted models, add `--online`. Relay then adds the Claude and Codex CLIs
if they are installed and logged in, and any provider whose API key is set in
the environment (see the table below). The quickstart above did not exercise
those tiers.

## How it compares

- **Aider** is the closest match: a terminal pair programmer with a repo map,
  git auto-commit and support for many models. It has more edit formats, more
  model integrations and a much larger user base. Relay adds ordered failover
  across local, subscription and API backends in one run, a saved run log that
  verifies offline, and acceptance tied to a check command you supply.
- **Claude Code** and **Codex CLI** are the vendors' own agents, with richer
  tools and interfaces, each tied to its provider. Relay can call either one as
  a backend tier and fall back to a local model when the quota runs out.
- **OpenHands** runs agents inside a Docker sandbox with a web interface. Relay
  has no container sandbox: its file tools stay inside `--root`, but the shell
  tool, when you enable it with `--allow-exec`, can reach any path your user can.
- **LiteLLM** and similar routers give you failover between model APIs without
  an agent loop. Relay builds failover and the agent into one zero-dependency
  command.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/relay.html)
walks through hash-anchored edits on a four-line file, the default-deny tool gate, the hash-chained run ledger and the prompt-injection probe. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Watch

[![Models do what training pays for: a narrated film, 2 min](https://harperz9.github.io/media/explainers/incentives/poster.jpg)](https://harperz9.github.io/explainers.html#incentives-h)

**[Models do what training pays for](https://harperz9.github.io/explainers.html#incentives-h)** (2 min, narrated, captioned). Relay accepts a run only when your own check passes, which is the guard this film argues for. The film page carries the transcript, the sources and recall questions.

## More commands

```
relay "explain this function" --file app.py
relay --agent "fix the off-by-one in paginate()" --root . --allow-write --auto-commit
relay --mcp                                # serve the agent to any MCP client (read-only)
relay --mcp --allow-write                  # ...and let its runs write under the launch root
```

## Reaches every endpoint (with your own credentials)

<p align="center"><img src="docs/art/endpoint-ladder.svg" alt="The endpoint ladder from prompt to cloud, with rungs tried in order and free tiers first." width="100%"></p>

One ladder, tried in order, failing over on exhaustion or error, free/private
tiers first so you only spend metered tokens when you have to:

| Tier | Reached by |
|---|---|
| **local** | a local server on `127.0.0.1:8765` with a `/generate` endpoint (`--serve-url`), then Ollama (the largest pulled model, or `--model`) |
| **plan / max** | the official CLI (`claude`, `codex`) using your subscription auth, started isolated from your project |
| **api** | `codex` / `claude` / `glm` / `gemini` / `deepseek` public APIs + `<PROVIDER>_API_KEY` |
| **provider** | a gateway (OpenRouter, ...) via `<PROVIDER>_PROVIDER_BASE_URL` |
| **cloud** | a cloud OpenAI-compatible endpoint via `<PROVIDER>_CLOUD_BASE_URL` + `_CLOUD_KEY` |

Legitimate by construction: keys come from the environment, subscriptions from
your own authenticated CLI, gateways from a base URL you set. Nothing is forged,
no cover identity is minted, no session token is harvested, no billing is evaded.
A missing credential just drops that tier from the ladder.

One rule inside that is worth stating, because it is the difference between a
gateway and a leak. A gateway rung points at an arbitrary base URL that you set,
so it may use only its own dedicated `<PROVIDER>_PROVIDER_KEY`. It never falls
back to that provider's official API key, because replaying your real credential
to a third-party URL is exactly the failure the rung exists to avoid. With no
provider key set, the gateway is called unauthenticated and the official secret
stays where it is. A rung whose credential is absent is never added to the ladder
in the first place, so a missing key is a shorter ladder rather than an error at
call time.

## Agent tools

`--agent` runs a permission-checked tool loop the model drives:

- **`repo_map`**: a compact code outline (Python via `ast`; JS/TS/Go/Rust/Java/
  C#/Swift/PHP/Ruby via patterns) so the model finds the right file.
- **`edit_file`**: precise search/replace where the target must match exactly
  once, so an ambiguous edit is refused, not guessed.
- **`edit_lines`**: hash-anchored edits. A `read_file` with `"hashed": true`
  returns every line as `<8hex>|<line>`, and the model edits by that anchor
  instead of by repeating the line. It is compact, and an anchor computed against
  a stale view will not match, so a mismatched edit fails closed rather than
  landing on the wrong line.
- **`edit_plan`**: a coordinated multi-file change applied as one all-or-nothing
  checkpoint. Every hash-anchored op is resolved first; if any anchor is stale,
  ambiguous, or overlaps another op, nothing is written. Each op carries a receipt
  (its resolved line, that line's pre-image, and the anchor) so a stranger can
  recompute the anchor and confirm the edit landed exactly where the plan said.
- **`apply_diff`**: applies a unified diff to one file, fail-closed. A hunk whose
  context does not match the current file exactly is refused with nothing written,
  so a model that emits diffs gets the same no-silent-misapply guarantee. Unlike a
  fuzzy applier, drift is a refusal, not a wrong-place edit.
- **`read_file` / `list_dir`**: confined to `--root`. `read_file` takes an
  optional `"hashed": true` for the anchored view above.
- **`write_file`**: off by default; enabled with `--allow-write`; confined to `--root`.
- **`run`**: off by default; enabled with `--allow-exec`. A shell can write, so
  `--allow-exec` implies write, and unlike the file tools `run` is not confined to
  `--root` (it sets only the working directory). A denylist refuses a few literal
  destructive spellings: a guardrail against a small model wrecking the tree, not
  a security boundary.

Two opt-in loop features, both witnessed:

- **`--interactive`**: prompt for approval before every mutating call. Each decision
  is a hash-chained ledger entry bound to the call's exact bytes, so the `.rvc` can
  prove a human gated the step and the approved bytes match the executed bytes. Off
  by default, and a headless run is byte-identical to one without it.
- **`--compact-budget N`**: once the prompt passes `N` tokens, fold older turns into
  one summary so the loop keeps running in any context window, pinning the task
  anchor and the policy text. Every fold records the folded-span and summary hashes
  on the ledger, and the untruncated trajectory stays there, so shrinking the prompt
  never loses the record.

## Watch mode: a marker comment, in any editor

No editor plugin, so it works the same in vim, Notepad, or a hex editor: drop a
comment with the marker anywhere in the tree and relay picks it up.

```bash
relay --watch --root . --allow-write     # polls for "RELAY:" comments; Ctrl-C to stop
```

```python
def add(a, b):
    return a - b  # RELAY: this should add, not subtract
```

Each marker becomes its own agent goal with its own witnessed ledger, through the
exact same gated tool loop as any other run. The model is told to remove the
marker itself via `edit_file` once it has acted, so even a change you triggered by
typing a comment, not a prompt, is never a bypass of the ledger. `--watch-marker`
changes the trigger string; `--watch-interval` the poll period.

## Project conventions, once

Drop an `AGENTS.md` or `CONVENTIONS.md` at your project root and every `--agent`
/ `--watch` run folds it into the system prompt automatically (verbatim, never
summarized, length-bounded so an oversized file degrades instead of blowing a
small model's context). `--no-conventions` opts out.

## Ambient repo context

`--agent`/`--watch` fold a bounded repo map into the system prompt automatically
(`--root`, stopped at 20 files and capped at 4096 UTF-8 bytes so it never grows
unbounded on a large tree): the model starts with the codebase's shape instead
of spending its first turn calling `repo_map` to ask for it. It can still call
`repo_map` itself for more detail or a subdirectory; this is a head start, not a
replacement. `--no-repo-map` opts out.

This closes a real, verified gap in *what context the model has* (Copilot's
agent mode does this too). It is not a claim about the small local model's
tool-use reliability, which is a separate, already-known limitation (see
Architect mode below). Live runs during development showed high run-to-run
variance in whether the model actually calls `edit_file` at all, on identical
input, with and without the ambient map. That variance predates this change and
is not attributed to it here.

## Architect mode: plan with one model, implement with another

```bash
relay --agent "add rate limiting to fetch()" --root . --allow-write \
      --architect claude-plan --online --check "pytest -q"
```

A planning turn runs first on the backend you name. It can be any tier Relay
already reaches: local, subscription, API, gateway, or cloud. Relay folds that
plan into the implementer's goal as an attributed proposal. The implementing
agent still gets the current project context, reads the real code, and may
adapt or ignore the plan if the code points to a better path. Bare
`--architect` uses the first healthy backend. Architect mode is currently
limited to plain single-run `--agent`; Relay refuses `--architect` with
non-agent modes, watch/MCP/probe/view/verify/bisect/health commands, and
`--best-of` until those paths have explicit planner semantics.

## A run log you can check

<p align="center"><img src="docs/art/accountability-lane.svg" alt="Eight stages from goal to certificate, ending in allow, refuted, or unverifiable." width="100%"></p>

Every turn, tool call, and result is appended to a **hash-chained session
ledger**. A saved run is tamper-evident: reload it and `verify()` re-derives the
chain (a broken chain is refused, not loaded). With `--auto-commit`, relay stages
only the files the ledger recorded as edits and carries the checkpoint in the
message, so the commit binds the witnessed edit set; unrelated or shell-written
working-tree changes are left out, never attributed to the run. Each model turn
also carries a content-addressed receipt whose id a stranger can re-derive from
the saved record.

## Accept a run only when your check passes

A witnessed trajectory proves *what* the agent did. It does not prove the edits are
*correct*: a model can finish confidently and leave a broken tree. Pass `--check`
and relay closes that gap: after the agent finishes, it runs your acceptance command
once, witnesses the result on the ledger, and **accepts** the run only if it passes.

```bash
relay --agent "fix the failing test in paginate()" --root . --allow-write \
      --check "pytest -q" --auto-commit
```

The check carries *your* authority, not the model's: it runs outside the tool
permission boundary and is never a call the model can emit or steer. A failed check means the run is not
accepted, `--auto-commit` is skipped (a broken tree is never committed on your
behalf), and the exit code is non-zero, so `--agent --check` works as a CI check over the
agent's own work. `accepted` = a provable trajectory whose acceptance check held.

`--test-cmd "pytest -q"` is the retrying form: on a failure the output goes back
to the model and it keeps working until the command passes or `--max-steps` runs
out. It needs `--allow-exec`. `--review` adds a second model pass that sees only
the diff and none of the author's log. It returns APPROVE or REQUEST_CHANGES,
or UNCLEAR when the reply does not start with either.

And the pass has to be *earned*. A rule-based reward-hacking guard reads the
witnessed edit set: if the agent made the check green by editing the test that grades
it, or by injecting a `pytest.skip` / `sys.exit`, the pass is flagged UNTRUSTED and
the run is not accepted. A gamed green is never committed. The flags ship with the
run under their own hash, re-checkable; the guard is non-learned and only ever turns
an accept into a refusal, never the reverse.

## Prompt-injection probe

Third-party data an agent reads (a file, a webpage, a tool result) can carry an
instruction that tries to make it exfiltrate, overwrite, or escape. relay's defense
is the boundary: tool output is data, never a command, and writes and exec are off by
default. `relay --probe-injection` measures that defense. It runs a fixed,
inspectable corpus of injection scenarios through the permission-checked executor, assuming the
worst case that the model was fully fooled and emitted exactly the smuggled call,
and reports **containment** with a re-derivable receipt. It exits non-zero if any
scenario is not contained, so it works as a CI check.

```bash
relay --probe-injection                 # safe default: every injection contained
relay --probe-injection --allow-exec    # honest: an open shell is a superset capability
```

It generates no attacks (the corpus is readable data) and it can fail, so it is a
real measurement, not a reassurance. Harden the defender, measure it, feed the
failures back.

## A run a reviewer can read

Every `--agent` run also ships a **reviewability projection** derived purely from the
witnessed ledger, in the terms a senior reviewer checks first: which files were
`edited_unread` (changed without ever being read), which edits no passing check
covered (`unverified_edits`), the failed-call scars, and a `reviewability` score over
read-before-write, verified, and clean-call ratios. Alongside it, a `risk` table tiers
each edit by mechanical signals (lines, nesting depth, branching, duplicate lines);
a high-tier edit **demands** a stronger receipt. These are facts, never generated
prose, so a surface can enforce them. Expert reviewers get the middle of the run, not
just its ending.

## Five ways to check a saved run

The witnessed ledger is the substrate for five checks a stranger can run offline.
The full capability matrix and the honest nulls are in
[docs/ACCOUNTABILITY.md](docs/ACCOUNTABILITY.md); the benchmark posture is in
[docs/BENCHMARKS.md](docs/BENCHMARKS.md).

- **See it.** `relay --view run.jsonl` draws the run as a hash-chained timeline.
  Flip one byte in the saved run and exactly one edge snaps red, verdict REFUTED.
- **Certify it.** `--cert run.rvc` writes a few-KB proof-carrying certificate;
  `python verify_cert.py run.rvc` re-derives ALLOW / UNVERIFIABLE / REFUTED offline,
  no model and no re-execution, with zero dependencies.
- **Select by proof.** `--best-of 8 --check "pytest -q"` runs the goal eight times
  and keeps the verified winner. A run that passed by editing the grader ranks below
  an honest run that scored higher.
- **Localize a regression.** `--bisect run.jsonl --root <clean> --check "pytest -q"`
  replays the witnessed edit set and names the first edit that broke the tests.
- **Ground the summary.** relay checks the final answer against the ledger: a summary
  that claims the tests pass over a failed check is REFUTED, even with an intact chain.

Those three verdicts are ordered, and the order is the point. `verify_cert.py`
returns REFUTED first, UNVERIFIABLE next, and reaches ALLOW only when nothing
earlier fired. A confirmed contradiction therefore outranks an inability to check,
and both outrank acceptance, so a clause the verifier cannot re-derive can never
be rounded up to a pass. The exit code follows: zero on ALLOW, non-zero on either
of the other two, which is what makes it usable as a check in someone else's CI.

<p align="center"><img src="docs/art/clause-ladder.svg" alt="The eight clause types a relay acceptance contract may carry, one to a row, with whether the standalone verifier that ships inside every certificate can re-derive each one. chain_intact re-derives before any clause is read, so a flipped byte is refuted whether or not the contract asked. check_not_gamed, no_claimed_history, no_edit and steps_approved re-derive from the file alone: the ledger carries the edits, the reasoning and the approvals they read. tests_pass, reviewability and claim_grounded need the in-tree verifier, because they read per-turn receipts, a diff-level reviewability pass and a syntax-level scan that the vendored file does not carry. Those three report unverifiable rather than assuming they hold." width="100%"></p>

Which clause sits in which row is not a matter of taste. Five of the eight
re-derive from the certificate alone, because the ledger inside it carries the
edits, the reasoning and the approvals those clauses read. The other three want
the per-turn receipts, the diff-level reviewability pass, or the syntax-level
scan for a reward hack, and none of those travel in the file. The vendored
verifier names them unverifiable and stops there.

## Use from an agent (MCP)

`relay --mcp` is a zero-dep stdio MCP server exposing `local_agent_health`,
`local_agent_chat`, `local_agent_run`, and the background `local_agent_start` /
`local_agent_status` / `local_agent_result` loop. Point Claude Code (or any MCP
client) at it to use relay as a fallback tier, e.g. keep working on local models
when a hosted quota runs out.

Write, exec and the root belong to whoever starts the server. Write and exec
are off by default, the root defaults to the directory the server starts in, and
a tool call cannot widen any of them:

```
relay --mcp                                # runs read and list files under the launch root
relay --mcp --allow-write                  # runs that ask may also write there
relay --mcp --allow-exec                   # runs that ask may also use a shell (implies write)
relay --mcp --root ~/work                  # runs stay inside ~/work
RELAY_ALLOW_EXEC=1 RELAY_MCP_ROOT=~/work relay --mcp    # grants from the environment
```

A flag or its variable grants; `1`, `true`, `yes` and `on` count as on, and an
unrecognized value stops the server at launch rather than guessing. A run gets
what it asks for and the launch granted, both: `local_agent_run` and
`local_agent_start` ask with `allow_write: true` or `allow_exec: true`, an
omitted argument asks for nothing (as in 0.2.5), and `true` cannot grant what
the launch did not. `allow_exec: true` also asks for write, and
`allow_write: false` turns exec off, because a shell can write. `check`,
`test_cmd` and the online `codex` and `claude` CLI tiers reach a shell, so they
need exec; a run that sets `check` without it is refused with
`EXEC_NOT_GRANTED`. A run's `root` must resolve inside the launch root, or the
call is refused with `ROOT_NOT_GRANTED`. `relay.status` and `relay.doctor`
report the grants and the launch root, and background runs keep the gate and
root they started with through `local_agent_status` and `local_agent_result`.

The file tools also leave the server's own files alone: they never read the env
file the remote entrypoint uses (`RELAY_ENV_FILE`, default `.env`), and never
write it, the run store (`RELAY_RUN_ROOT`), the session store
(`RELAY_SESSION_DIR`) or anything under a `.git` directory. They also refuse
writes into agent and editor configuration (`.claude`, `.codex`, `.cursor`,
`.vscode`, `.gemini`, `.agents`, `.opencode`, `.mcp.json`), whose hooks, tasks
and MCP servers run the next time a tool opens the tree.

Saved sessions live in `RELAY_SESSION_DIR`, or in a per-user folder when it is
unset (`%LOCALAPPDATA%\relay\sessions` on Windows, `~/Library/Application
Support/relay/sessions` on macOS, `$XDG_DATA_HOME/relay/sessions` or
`~/.local/share/relay/sessions` elsewhere), never the folder the server starts
in. `local_agent_sessions` takes a `session_id` only as a bare name of letters,
digits, `.`, `_` and `-`, and refuses anything else with `INVALID_ARGUMENT`. A
file that will not parse is skipped and counted in `skipped`. The stdio
`relay.doctor` reads an env file only when `RELAY_ENV_FILE` names one.

What relay's children see. The shells and CLI tiers relay starts get an
environment allowlist, not the server's whole environment: the platform base
(`PATH` with absolute entries only, the system and profile folders), and for
shells a fixed set of toolchain variables such as `VIRTUAL_ENV`, `JAVA_HOME` and
`CARGO_HOME`. No provider key reaches `run`, `test_cmd`, `check` or a CLI tier.
To pass more, list the names in `RELAY_CHILD_ENV` (comma separated) in the
environment that starts relay. On Windows a shell no longer finds a program in
the root by bare name; call it as `.\tool`. The `git` that `--auto-commit` runs
keeps the whole environment, since it reads your GPG, SSH and git settings from
it.

A child's `PATH` also loses every entry that reaches the folder the child works
in or the server's folder: an entry naming that folder or a folder below it,
another spelling of it, or a junction or symlink to it. That keeps a program
planted in a project from standing in for an installed `claude`, `codex`, `git`
or shell tool, or for a program git starts itself, such as a clean filter or
`gpg`; the 0.5.0 changelog lists the limits. A bisect check runs in a copy of
the project, and guards the project it copied. A tool in a project's
`.venv/bin` or `node_modules/.bin` then needs its path. The folder that holds
the interpreter relay runs on stays on `PATH`, so relay started from the
project's virtual environment keeps that environment's tools (`.venv/bin`, or
`.venv\Scripts` on Windows). Tools in other folders inside the project, such
as a Windows conda environment's `Scripts` and `Library\bin`, need their path.

The `claude` and `codex` CLI tiers start isolated: the executable resolves to an
absolute path (`RELAY_CLAUDE_CLI` and `RELAY_CODEX_CLI` override it and must be
absolute), the child runs in a new empty folder, the prompt goes on stdin, and
each CLI gets the flags that keep project settings, hooks, MCP servers,
instruction files and skills out. For `claude` that is `--setting-sources user
--strict-mcp-config --tools ""`. For `codex` it is `exec` with
`--ignore-user-config`, `--ignore-rules`, `--ephemeral`, a read-only sandbox,
hooks, plugins, memories and apps disabled, and project docs and skills off.
Those flags were probed on claude 2.1.251 and codex 0.144.6, and
`relay.doctor` reports each tier's row as `PASS` only on the tested version.
They still need exec. A CLI tier whose isolation profile is not proven starts
only when the launch also names it in `RELAY_ALLOW_EXEC_CLI`, and its doctor
row stays `WARN`.

The limits to plan around: the shell is not path-confined. With exec granted,
`run`, `test_cmd` and `check` start in `root` and can read and write any path
the server's user can. Write is also a route to code execution: a file written
under the root runs the next time something executes it there, such as a build
script, a test, or a shell profile when the root is a home directory. Launch the
server over a workspace you would let its callers edit, not over relay's own
checkout or your home directory, and grant exec only to a server whose callers
you would trust with that account.

The MCP run tools accept the same bounded routing and acceptance dials as the
local CLI agent path: `backend`, `model`, `max_tokens`, `check`, `test_cmd`, and
`compact_budget`, in addition to `goal`, `root`, `allow_write`, `allow_exec`,
`max_steps`, and `online`. Results carry a `relay.mcp-run-request/v2` binding
with the admitted effective backend/model/gate choices, the launch grants
(`granted_allow_write`, `granted_allow_exec`, `granted_root`), the arguments as
sent (`null` when omitted), what was asked beyond the grant
(`grant_shortfall`), whether the remote surface refused exec, the protected
paths, and hashes of the goal/check commands. Results also include the last witnessed
assistant backend/model receipt when a run reaches the agent loop.

For background runs, set `RELAY_RUN_ROOT` to make progress durable across a
server restart. `local_agent_start` snapshots the run record when it starts and
the agent loop asks for a durable checkpoint after witnessed progress, so a
fresh server can reload the partial ledger and report `interrupted` instead of
silently losing the entries. A partial checkpoint is only bytes-on-disk evidence
for observed progress; it is not a completed result, a rollback guarantee, or an
acceptance verdict. `local_agent_result` reports `done` only after the final
result record is persisted.

## Library

```python
from relay import LocalAgent, available_backends, build_endpoints, run_agent

agent = LocalAgent(backends=available_backends() + build_endpoints())  # local + online
print(agent.send("hi")["content"][0]["text"])
```

`relay.cascade` asks a local classifier a yes-or-no question first and calls your endpoint only when it abstains, writing each answer to the session ledger. The bundled "is this test failure flaky?" classifier missed its measured bar, so the default sends nearly every question to the endpoint; see [docs/CASCADE.md](docs/CASCADE.md).

## License

Relay is fair-source: open to read, run, and build on, with commercial use reserved so the project can fund its own development. See [LICENSE](LICENSE).

## What this believes

This tool is one part of a family that holds a single belief steady across
every surface: knowledge open to anyone who can attain the means; acceptance
decided by external checks, never reputation; every result re-runnable;
honest nulls first-class; ownership earned by comprehension; learning woven
into the work. The full text lives in [CREDO.md](CREDO.md).
The long form of this belief: [The Unbundling](https://github.com/HarperZ9/flywheel/blob/main/docs/essays/2026-07-13-the-unbundling.md).

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).

## Local client packages

The additional [client package](client-plugin/README.md) includes portable plugin metadata and a Windows x64 MCPB/ZIP build. Version 0.6.0 first attached these packages to its GitHub release, and a published GitHub release for each later version carries packages built from that tag. Native packages carry their Python runtime. No publisher backend is required.
