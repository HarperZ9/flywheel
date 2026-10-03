# Flywheel mod for Claude Code (experimental)

Not published. Not yet run inside Claude Code. Mods need Claude Code 2.1.287 or
later; this mod has been tested only in a stand-in runtime and against the real
Flywheel pre-action monitor run as a subprocess.

## What it does

- **Holds risky calls.** Bash, PowerShell, Edit, Write, MultiEdit and
  NotebookEdit calls that a risk pre-filter flags go to the Flywheel pre-action
  monitor. A hold returns `{ deny }` with the monitor's reason and hold id, and
  the tool never runs. A pass hands the call on, so Claude Code's own permission
  check still runs.
- **Writes a receipt per turn.** One hash-chained JSON line per turn in
  `.flywheel/mod-receipts/<session>.jsonl`: each screened call's `tool_use_id`,
  input digest, pre-filter hits, monitor verdict, hold id and outcome, plus file
  hashes before and after edits.
- **Shows a status line** above the prompt: held and passed counts and the last
  receipt hash.
- **Never approves.** It registers no `tool.check` hook and never answers with a
  decision, a result or consent. Every answer is what Claude Code's core returned
  or exactly `{ deny }`.

Two scripts come with it:

- `node scripts/audit-mods.mjs` reads your installed mods and reports approval
  patterns (HIGH: a hook that answers allow or sets consent). Read-only. Exits 1
  on any HIGH finding.
- `node scripts/rederive.mjs <receipts.jsonl> <transcript.jsonl>` re-derives the
  receipts from a Claude Code transcript and prints MATCH or DRIFT.

## Settings

`monitor_source` is required: the folder that holds Flywheel's `harness/`
package. When it is empty, every screened call is denied as unchecked, because
importing `harness` from whatever Python finds first could load an unrelated
package with the same name. Other settings (`python`, `monitor_home`,
`screen`, `on_unavailable`, `status_site`, `receipts_dir`) are described in
`.claude-plugin/plugin.json`.

If the monitor cannot answer, the call is denied with a visible reason.
`on_unavailable: pass` makes that one case fail open and logs it.

## Tests

```
npm test
```

45 tests: the mod in a stand-in runtime with a scripted monitor, the library
functions, the audit script, re-derivation, and five tests against the real
monitor in this repository. False-success controls: a held call returns exactly
`{ deny }` and the tool never runs; a fixture mod that always passes is caught;
across monitor behaviors and call types every answer is core's result or
`{ deny }`.

Monitor cost per screened call, measured on one Windows machine (n = 20): median
411 ms, p90 457 ms.

## Known gaps

- Never run in Claude Code. `claude plugin validate .` and `claude plugin test .`
  on 2.1.287 or later come before any release.
- MCP tools and WebFetch are not screened yet.
- Each screened call starts a new monitor process; a long-lived monitor is not
  built.
- A hold is approved with `flywheel monitor approve <hold_id>` from a real
  terminal. That round trip is untested.
