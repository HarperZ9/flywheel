# Pre-action monitor: owner config, anti-tamper witnesses and OpenShell

The pre-action monitor checks every agent tool call before it runs and holds the
risky ones for you. This page covers four things you set up once:

1. the owner config, which sets the hosts your agent may reach;
2. where the monitor keeps its state, and how a witness outside the agent
   notices a skipped hook or a rewritten record store;
3. importing OpenShell activity logs as sealed records;
4. running a hooked Claude Code or Codex session inside an OpenShell sandbox.
   This part is optional.

## 1. Owner config

Write `owner.json` under your Flywheel home (`~/.flywheel/preaction/owner.json`
unless `FLYWHEEL_HOME` points elsewhere). The hook and the built-in executor
both load it.

```json
{
  "schema": "flywheel.preaction-owner/v1",
  "allow_hosts": ["ci.internal.example"],
  "owned_hosts": ["db.internal.example"],
  "fetch_hosts": ["docs.mycompany.example"],
  "canaries": ["CANARY-7731"],
  "witness_dir": "/home/me/.flywheel-witness",
  "head_export_every": 25
}
```

- `allow_hosts`: any call may reach these hosts, uploads included.
- `owned_hosts`: systems you own, so logging into them is not held.
- `fetch_hosts`: hosts a read-only fetch may reach. A shipped list of
  documentation hosts (Python, MDN, Rust, Node, Go, Microsoft Learn, GitHub
  Docs and others) is added unless you set `"use_default_fetch_hosts": false`.
- `canaries`: decoy tokens. Any call that carries one is blocked.
- `protected_paths`: extra paths the agent must not write. The owner file
  itself and the witness directory are always protected, wherever they live.
- `monitor`: monitor settings (judge, thresholds, hold expiry).
- `expected_rules_digest`: the rule-pack digest you approved. A different
  installed pack blocks every call.
- `witness_dir`, `head_export_every`: see section 2.

### Optional rule: hold side-effecting tool names

The rule `scope-escape/004` holds a tool call whose name says it posts, sends,
deletes, updates, trashes, resets, pays, transfers or starts a server, such as
`send_reply`, `delete_email` or `start_mcp_server`. It is off by default. Turn it
on in the owner file:

```json
{ "monitor": { "optional_rules": ["side-effect-tools"] } }
```

Turning it on changes the monitor config digest, so a pinned monitor blocks
until you pin again. The shipped rule-pack digest does not change.

Why it is off by default: on 48 side-effecting tool names from installed tool
servers and a published test set, it held 27 (Wilson 95% interval 0.42 to
0.69), short of our 0.80 bar. Names such as `create_pull_request`, `forward` and
`add_issue_comment` pass it. On 50 read-only names it held none (upper bound
0.07). How often it would stop a working agent per hour is unmeasured. A name is
weak evidence of effect: a tool named `fetch_data` can still delete.

Run `flywheel monitor owner` to print the effective config and its digest. Point
the hook at a specific file with `flywheel monitor install claude-code --home
<dir> --owner-config <file>`.

With no file, reading documentation works without a hold. A fetch counts as
read-only when it is WebFetch, or a single `curl`, `wget` or
`Invoke-WebRequest` command that uses only a short list of options (quiet,
follow redirects, fail on error, timeouts, retries and an output file),
names only http or https URLs, writes no file outside the working directory
or into a hidden folder, has no pipe, redirect or variable, and keeps the
query string to 128 characters. Any other option holds, so an upload, a
proxy, a changed address, a header, a long query string, a pipeline and an
unlisted host all still hold.

A file that does not parse, names an unknown field or lists a wildcard host
stops every call until you fix it. If you pin the monitor (`pin_config`), an
edit to the owner file blocks every call until you pin again.

Measured on the review's held-out bank of 30 ordinary developer calls: 0 holds
before and after (Wilson 95% interval 0.00 to 0.11). That bank has no network
calls, so it shows no regression but cannot show the change. On a 10-call
documentation-fetch bank written with this change: 10 of 10 held before, 0 of
10 after. On a 10-call network misuse bank written with it (uploads to doc
hosts, long queries, pipes, unlisted hosts): 10 of 10 stopped before and after.
The harmful held-out bank stays at 24 of 30. Both network banks are small and
written by the author of the change; they are not held-out. Rerun with
`python scripts/eval_preaction_banks.py`.

## 2. State outside the agent, and the witness

**Where state lives.** The built-in executor keeps its store under
`<FLYWHEEL_HOME>/preaction/executor/<workspace-name>-<digest>`, outside the
workspace the agent writes to. Give the hook a `--home` outside your projects
too. The monitor also protects its own home by rule: a write or shell command
that names it is blocked.

**What "outside the agent's reach" means here.** `flywheel monitor coverage`
prints a domain column for every attach point. Every tool-call path today is
`inside`: the hook is a child of the agent harness and runs as your OS user,
so an agent with an unrestricted shell could still reach its files. The
witnesses are `outside`. The verifier reports ALLOW records by domain, because
an inside ALLOW is weaker evidence than an outside one.

| Id | Domain | What it does |
| - | - | - |
| W1 | outside | Joins harness transcripts against pre records |
| W2 | outside | Imports OpenShell OCSF records (section 3) |
| W3 | outside | Copies the store's chain head out at every stop and every N records |

**Chain-head export.** Set `witness_dir` in the owner config. The hook then
appends the store's head (sequence number and seal) to its own sealed chain in
that directory at every hold or block and every `head_export_every` records. If
someone rewrites the store later, even with a valid chain, the exported head
no longer matches and the witness reports DRIFT.

**Transcript witness.** Claude Code and Codex write their own transcript of every
tool call the model made. The hook does not write those files. Run the witness
from your own terminal or a scheduled task, never from the agent:

```bash
flywheel monitor witness --home <monitor-home> --witness-dir <witness-dir> \
  --transcripts ~/.claude/projects/<project>/ ~/.codex/sessions/
```

It reads only tool-call items and never reads thinking or reasoning content.
Any tool call older than 60 seconds (`--grace`) with no pre record means the
hook was skipped, disabled or killed for that call, and the witness reports
DRIFT. With no readable transcript it reports UNVERIFIABLE, never MATCH. Exit
codes: 0 MATCH, 1 DRIFT, 3 UNVERIFIABLE.

Limits: without a sandbox, the transcripts and the witness directory sit under
your OS user, so an agent that can run any shell command could edit them too.
The witness then catches a skipped hook unless the agent also rewrites the
harness transcript and the witness directory. The join assumes the hook's
`tool_use_id` equals the transcript's tool call id; this was tested on fixture
transcripts, not on a live session. A mismatch shows as DRIFT, not as a false
MATCH.

## 3. OpenShell activity logs as sealed records

```bash
flywheel monitor import-ocsf <ocsf.jsonl> --home <import-home> [--metrics <scrape.prom>]
```

Each OCSF event becomes one sealed, chained `flywheel.openshell-event/v1`
record: Allowed is MATCH evidence, Denied or Blocked is BLOCK evidence, a
Detection Finding (class 2004) is a NOTICE. A summary record closes each
import. Re-importing a file adds nothing. `flywheel monitor verify
<import-home>` re-walks the chain offline.

Completeness is UNVERIFIABLE unless all of these hold: you pass a gateway
metrics scrape; `openshell_ocsf_log_dropped_total`,
`openshell_ocsf_log_writer_errors_total` and
`openshell_ocsf_log_recovery_discarded_bytes_total` read zero; queued equals
written; every event came from the gateway; no line was malformed; and the
file holds no lifecycle event (a restart resets the counters).

Which file to read. OpenShell writes network, HTTP and process events from the
sandbox supervisor into the sandbox-local file
(`/var/log/openshell-ocsf.YYYY-MM-DD.log`). The gateway JSONL holds
gateway-origin events such as policy changes. Pull the supervisor file from
the host with `openshell sandbox download`; the agent can read it but not
write it under OpenShell's default read-only `/var/log`. It has no loss
counters, so its completeness is always UNVERIFIABLE. The seal proves what
Flywheel read, not what OpenShell saw: OpenShell records are unsigned at
source.

## 4. Optional: run a hooked session inside OpenShell

OpenShell adds a kernel filesystem boundary, a network fence and credential
isolation around the agent. The hook still makes every hold decision; OpenShell
backs it up when a rule misses. Today this runs on Linux and macOS, and on
Windows only inside WSL 2, which OpenShell marks experimental. Native Windows
needs OpenShell's MXC driver, which is still in review. Without OpenShell, the
monitor works as described above.

```bash
flywheel monitor sandbox claude-code --workspace . --out ./openshell-plan        # print only
flywheel monitor sandbox claude-code --workspace . --out ./openshell-plan --run  # create and start
```

The command writes an OpenShell policy built from your owner config. Every
endpoint is `enforcement: enforce`, because OpenShell's default is audit,
which allows. Fetch hosts are read-only and allow hosts are read-write. `/etc`
stays read-only. The command then creates a detached sandbox with your
workspace uploaded and starts the agent with `openshell sandbox exec`. On
Windows it prints the WSL form of each command.

Bake the hook into the image as a managed settings file under `/etc`
(`/etc/claude-code/managed-settings.json` for Claude Code), so the agent
cannot edit its own hook block:

```dockerfile
COPY managed-settings.json /etc/claude-code/managed-settings.json
RUN pip install flywheel-verify
```

Keep the witness on the host. Download the monitor store and the transcripts
with `openshell sandbox download`, then run `flywheel monitor witness` and
`flywheel monitor import-ocsf` there. The witness directory then sits outside
the sandbox boundary, where the agent cannot write.

Before you rely on it, turn off two defaults that send data out: set
`OPENSHELL_TELEMETRY_ENABLED=false` on the gateway, and remove
`statsig.anthropic.com` and `sentry.io` from the Claude Code provider profile
if your policy forbids that traffic.

Not yet tested: these commands follow OpenShell's documentation and were
checked against a stand-in binary, not a running gateway.

Does not prove: that the monitor catches misaligned actions. These pieces make
a skipped hook and a rewritten store visible, and narrow what the agent can
reach. They do not show that every risky call is held.

## 5. Upgrading, scope and known limits

### After an upgrade that changes the rule pack

If your owner file pins `expected_rules_digest`, a new rule pack blocks every
call with `rules_digest_mismatch` until you re-pin. That is the intended
fail-closed behavior.

1. Run `flywheel monitor owner`. It prints `installed_rules_digest`.
2. Check that it matches the digest printed in the release notes.
3. Put that value in `expected_rules_digest` in your owner file.

Records sealed under the old rule pack stay sealed and chained. `flywheel
monitor verify` reports them as unverifiable, because the new rules cannot
re-derive verdicts made under the old ones.

### Scope: single-agent runs

The monitor sees the calls of the agent it is attached to. It does not follow
data between runs: if one run writes a note into a shared cache or folder and
another run reads it and acts on it, the monitor judges each call on its own and
does not connect the two. Use it to watch one agent at a time. Runs that share
writable state need separate controls on that state.

### Known limits

- A prompt or note that mentions a web address off your allowlist in plain text
  is held, even when nothing would fetch it. In one test, 10 of 10 ordinary
  prose prompts that named such an address were held. Add the host to
  `allow_hosts` or `fetch_hosts` if this gets in your way. A fix needs a design
  change and is not in this release.
- A request body split across several calls so that no single call shows a URL
  can pass. The egress proxy is the complete control for outbound traffic.
