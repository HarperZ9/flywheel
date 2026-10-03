# Flywheel mod for Claude Code (experimental)

This mod puts the Flywheel pre-action monitor in front of Claude Code's shell and file-edit tools.
A call the monitor holds never runs, and Claude reads the reason and the hold id.
Every turn leaves a hash-chained receipt you can check against the session transcript later.

It needs a Claude Code build with mods (function hooks). It was run on Claude Code 2.1.286.

## Install

In Claude Code:

```
/plugin marketplace add HarperZ9/flywheel
/plugin install flywheel-mod@flywheel-skills
/plugin configure flywheel-mod@flywheel-skills
```

From a shell, the same install with the one required setting:

```
claude plugin marketplace add HarperZ9/flywheel
claude plugin install flywheel-mod@flywheel-skills --config monitor_source=/path/to/flywheel
```

`monitor_source` is the folder that holds Flywheel's `harness/` package. Use a clone of
`https://github.com/HarperZ9/flywheel`. Released `flywheel-verify` packages up to 1.2.1 do not
include the pre-action monitor. The mod also needs a Python 3 interpreter on the machine; set
`python` if `python` is not the right command.

## What it does

- **Holds risky calls.** A risk pre-filter reads each Bash, PowerShell, Edit, Write, MultiEdit
  and NotebookEdit call. A flagged call goes to the Flywheel pre-action monitor. A hold returns
  `{ deny }` with the monitor's reason and hold id, and the tool never runs. A pass hands the call
  on, so Claude Code's own permission check still runs.
- **Writes a receipt per turn.** Each turn appends one hash-chained JSON line to
  `.flywheel/mod-receipts/<session>.jsonl`. The line records each screened call's `tool_use_id`,
  input digest, pre-filter hits, monitor verdict, hold id and outcome, plus file hashes before
  and after edits.
- **Shows a status line** above the prompt: held and passed counts and the last receipt hash.
- **Never approves.** It registers no `tool.check` hook and never answers with a decision, a
  result or consent. Every answer is what Claude Code's core returned or exactly `{ deny }`.

Two scripts come with it:

- `node scripts/audit-mods.mjs` reads your installed mods and reports approval patterns. A HIGH
  finding is a hook that answers allow or sets consent. Read-only. Exits 1 on any HIGH finding.
- `node scripts/rederive.mjs <receipts.jsonl> <transcript.jsonl>` re-derives the receipts from a
  Claude Code transcript and prints MATCH or DRIFT.

## Settings

`monitor_source` is required. When it is empty, every screened call is denied as unchecked. An
unpinned `import harness` could load an unrelated package with the same name, so the mod never
guesses.

If the monitor cannot answer, the call is denied with a visible reason. `on_unavailable: pass`
makes that one case fail open and logs it. The other settings (`python`, `monitor_home`,
`monitor_owner_config`, `monitor_timeout_ms`, `monitor_deadline_seconds`, `screen`,
`status_site`, `receipts_dir`) are described in `.claude-plugin/plugin.json`.

A held call is decided from your own terminal with `flywheel monitor approve <hold_id>`.

## What was run on Claude Code 2.1.286

**Validation.** `claude plugin validate` passes with no notes. It reports the hooks
`session.start`, `tool.call` for the six guarded tools, `turn.complete` and `ui.render` for
`AbovePrompt`.

**Engine tests.** `claude plugin test integrations/claude-code-mod` runs 11 tests against the
engine itself, and all 11 pass. The tests in `tests/engine.test.ts` cover these paths:

| Test | What it shows |
| :-- | :-- |
| held call | `curl -sI https://example.com` comes back denied with the hold id, and the tool never runs |
| benign call | `ls -la` runs without a monitor run |
| `screen: all` | a benign call goes to the monitor, which passes it, and it runs |
| no `monitor_source`, `on_unavailable: deny` | denied as unchecked; the tool never runs |
| no `monitor_source`, `on_unavailable: pass` | the call goes through |
| receipt | two turns write two lines; each hash recomputes and links to the line before |
| band | the status line draws on the terminal and desktop surfaces |

A test has no process, so the test answers the monitor run. For the held call it answers with
the exact bytes the real monitor printed for that command against the shipped rule pack, rule
`egress/002`.

**Paired mutations.** Each assertion was checked against a deliberately broken copy of the mod:

| Break | Tests that failed |
| :-- | :-- |
| `tool.call` hook removed | held call, `screen: all`, unchecked deny, receipt, band, and 2 older tests |
| hold turned into a pass | held call, receipt, band, and 1 older test |
| `on_unavailable` inverted | both unchecked tests, and 1 older test |
| benign call denied | benign call |
| receipt writer removed | receipt |
| hash chain link dropped | receipt |
| band hook removed | band |

**Live session.** A headless session (`claude -p --permission-mode default`) ran with the mod
installed from this repository's marketplace and `monitor_source` set with `--config`. A scratch
driver plugin issued two Bash calls through the hook chain at turn start. The debug log shows:

- the mod's hooks module loaded with `session.start, tool.call, turn.complete, ui.render`;
- for `curl -sI https://example.com`, the monitor exited 2 in 438 ms, and the mod answered
  `tool.call` with the hold text and hold id, so nothing beneath it ran;
- for `git --version`, the mod passed the call on unscreened, and Claude Code's own permission
  check refused it;
- `turn.complete` wrote one receipt line. Its hash chain verifies. Its input digest for the held
  call equals the `args.sha256` in the monitor's own hold record.

Limits of that run: the calls came from a driver plugin, so no model turn chose them. Plugin calls
are not transcript rows, so `rederive.mjs` reports the held call as missing from the transcript.
A held call issued by the model in a live session has not been observed yet.

The Node suite (`npm test`, 45 tests) still runs the mod in a stand-in runtime and runs the real
monitor as a subprocess. CI runs it on every pull request.

## Data and privacy

The mod makes no network call and reads no environment variable. It sends nothing off the
machine. On disk, in the project folder by default:

- `.flywheel/mod-receipts/`: digests, rule ids, verdicts, hold ids, the monitor's reason text and
  the paths of edited files. No command text and no file content.
- `.flywheel/monitor/`: the monitor's own records. For a held call this includes the call's
  arguments, so the owner can review the hold.

It starts one subprocess per screened call: the configured Python running the monitor from
`monitor_source`. The first receipt in a new folder may start one more Python process to create
the folder.

## Directory criteria

The four attestations the Claude plugin directory asks a submitter to make, and where this mod
stands on each:

1. **Follows the Software Directory Terms and Policy.** The mod adds holds and never approves a
   call, so it cannot widen what Claude may do. Its receipts hold digests, not command text. One open item: the
   directory's pre-submission checklist asks that everything a hook runs live inside the plugin
   folder. This mod runs the Flywheel monitor from `monitor_source`, outside the plugin folder.
   Until the monitor ships inside the plugin, this attestation is not met.
2. **The privacy statement is accurate.** The mod connects to no remote service, so no hosted
   privacy policy applies. The section above lists everything it writes and starts, checked
   against the live run.
3. **No credential exfiltration and no undeclared code.** Claude Code loads the declared hooks
   module, and the module starts only the monitor the user configures. It reads no credentials
   and makes no network call. Tool arguments go to the local monitor process on standard input
   and stay on the machine.
4. **Contact.** Support and security reports go to the issue tracker at
   `https://github.com/HarperZ9/flywheel/issues`.

## Known gaps

- MCP tools and WebFetch are not screened yet.
- Each screened call starts a new monitor process (about 0.4 to 0.9 s in the live run). A
  long-lived monitor is not built.
- Claude Code reports a tool error and a refusal by its own permission check to mods in the same
  way, so the receipt records both as `error`.
- The approve round trip (`flywheel monitor approve`, then the call again) is untested.

## License

Functional Source License 1.1 with an MIT future license (`FSL-1.1-MIT`), the same license as
Flywheel. The full text is in [LICENSE](LICENSE). Each version becomes MIT two years after its
release.
