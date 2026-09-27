# Capture hooks for Claude Code and Codex

Mount one hook module in Claude Code or Codex and every turn you run there
leaves a receipt in your Flywheel store. When a turn cannot be recorded, the
client tells you in the same turn, and Flywheel keeps a small record so the
session can be recovered later.

## Mount

```
flywheel traces hooks print-mount
```

prints the exact blocks for your interpreter. For Claude Code they look like
this (in `settings.json`, or a project `.claude/settings.json`):

```json
{"hooks": {
  "UserPromptSubmit": [{"hooks": [{"type": "command",
    "command": "\"<python>\" -P -E -m harness.capture_hooks prompt --client claude-code"}]}],
  "Stop": [{"hooks": [{"type": "command",
    "command": "\"<python>\" -P -E -m harness.capture_hooks stop --client claude-code"}]}]
}}
```

Codex takes the same blocks in `hooks.json` with `--client codex`. Flywheel
never edits a client's settings. `--home <path>` on the mount line names a
Flywheel home other than the default.

Hooks run inside the project folder. `-P` keeps that folder off Python's
import path and `-E` ignores `PYTHONPATH`, so a repository that holds its own
`harness` package, or a settings `env` block, cannot replace the hook. The
doctor fails a module mount that lacks them (`-I` also passes).

Check the result with:

```
flywheel traces doctor
flywheel traces doctor --synthetic
```

`doctor` lists your mounts, checks the channel to the gateway and shows
failures and suppressions. `--synthetic` records one synthetic turn through
the hook module itself. The doctor never runs a command taken from a
settings file, and it never prints a value from one other than the hook
entries and Claude Code's `cleanupPeriodDays`; from `env` blocks it reports
only the names of `FLYWHEEL_*` variables.

## What a turn sends and keeps

By default the hooks send no text. The prompt hook draws a random 32-byte
salt and sends a commitment, `sha256(tag, 0x00, salt, prompt)`, with the
salt; the Stop hook does the same for the final answer. The gateway pairs the
answer with its prompt by Claude Code's `prompt_id` or Codex's `turn_id`,
else first in, first out within the session, and chains a receipt
(`flywheel.turn-receipt/v2`) into `store.db`. The receipt holds the two
commitments, the pairing mode and segment, and a session ref keyed with your
custody key. It holds no text, no URL, no path and no plain digest, and its
id is random. The salts sit in a turn record under
`state/captured-turns/`, encrypted where an OS key store is available. To prove a turn later, reveal the text and the
salt; anything else learns nothing from the receipt.

- A continued Stop (`stop_hook_active`) adds a segment to the same prompt.
- A prompt with no answer within `pending_ttl_hours` (24 by default) becomes
  an unpaired turn, checked whenever the prompt or Stop hook reaches the
  gateway. `status` only reads, so it does not run this check.
- A Stop with no prompt is recorded as `unpaired`, with no prompt
  commitment.
- The final answer is the text the client hands the hook. Tool calls, tool
  results and reasoning are not in it; they are in the client's transcript.

`flywheel traces capture content on` keeps the prompt and answer text too,
in the turn record, a second copy beside the client's own transcript. It is
encrypted where an OS key store is available (DPAPI on Windows, the keychain
with the `encryption` extra on macOS and Linux) and kept in plaintext
otherwise; the confirmation and `status` say which. It takes effect only after you confirm it (see owner presence in
TRACE-OWNERSHIP.md). The gateway decides what capture does: an edited
`trace-capture.json` stays pending until confirmed, the prompt hook says so,
and the hooks never read the file.

`flywheel traces capture archive on` imports each Claude Code session's
transcript when it ends, into custody (encrypted where an OS key store is
available). Codex sessions are not archived, and `print-mount` gives Codex no
`SessionEnd` hook. The `SessionEnd` hook sends only the client and the
session id; the gateway finds the transcript under its own Claude Code
folder, refuses links, network paths, device names and stream names before
opening anything, and imports it in the background so the hook stays within
Claude Code's time budget. It accepts one request per session per minute. If
the gateway is down, the hook records the session id whatever the archive
setting, since it cannot ask the gateway; `flywheel traces import --pending`
imports those sessions later only while the archive is on.

`flywheel traces capture freeze on` turns on URL freezing, separately from
content capture. The prompt hook then sends the URLs it finds (at most five)
and nothing else of the prompt. The gateway refuses any URL with a user name
and password or a credential-bearing parameter (signed storage links, OAuth
codes, access tokens), counts it and echoes nothing of it. It fetches the
rest by resolving each host once, refusing private and loopback addresses,
connecting to the address it checked, ignoring proxy variables and checking
every redirect again (shared 100.64.0.0/10 addresses, which tailnets use,
are refused as well), then keeps each page (encrypted where an OS key store
is available) and hands Claude Code a manifest of what it froze. That
manifest, the URLs and their sha256 digests, goes into the model context and
so to the model provider. The Stop hook never fetches. The same fetcher now
serves `POST /api/snapshot`, so a fetch that only worked through a proxy
fails there too.

`POST /api/scaffold` stays for other callers with its bearer authentication,
and still freezes the URLs a prompt names; the hooks no longer use it.

## How the hook finds and trusts the gateway

- **The home.** From `--home`, else a pointer file the gateway writes in a
  per-user folder that the hook finds through the operating system, else your
  profile folder plus `.flywheel`. `FLYWHEEL_HOME` is only compared: a
  different value stops the hook with `HOME_MISMATCH`, so a repository's
  settings cannot redirect capture. A home inside a git work tree, or a
  `--home` inside the working directory, stops it with `HOME_IN_WORKTREE`.
- **The gateway.** From `gateway.endpoint` in the home, written by the gateway
  after it binds and removed when it stops. There is no fallback port: with no
  file, or a file naming a process that is not running, the hook reports
  `GATEWAY_NOT_RUNNING` and connects nowhere. Only `127.0.0.1` and `::1` are
  accepted; remote capture is not offered, and `FLYWHEEL_GATEWAY_URL` and
  `FLYWHEEL_CAPTURE_ALLOW_REMOTE` are ignored.
- **The listener.** On Windows the hook reads the TCP listener table, requires
  the listening process to be the one the endpoint file names, and requires it
  to run as your user. On Linux it requires the listening socket's uid to be
  yours. On macOS this check is skipped and the proof below carries the
  guarantee.
- **The proof.** Before sending anything, the hook sends a hello with a random
  nonce and no credential. The gateway answers with a proof, an HMAC under a
  key derived from the gateway token, bound to both nonces and to the address
  and port it bound. A listener that does not know the token, or relays the
  hello to the real gateway on another port, fails with `SERVER_PROOF_FAILED`
  and receives no token and no body. A gateway answering more than 20 hellos
  a second answers 429; the hook retries once, then reports
  `HELLO_RATE_LIMITED`. Any local account can use up that budget, so capture
  can be delayed by another account; it is named as such, not as an impostor.
- **Each send.** Every request opens its own connection (the gateway speaks
  HTTP/1.0), so the listener check runs again right before each request with
  a body.
- **Signed requests.** Each request carries an HMAC signature over method,
  path, body digest, time, a fresh nonce, the server nonce and the address.
  The token itself never crosses the socket. The gateway refuses a stale time,
  an unknown server nonce and a replayed nonce.
- **The port.** On Windows the gateway binds exclusively, so no second socket
  can share its port while it runs.

## When capture fails

- Claude Code Stop and SessionEnd hooks: exit 1, empty stdout and one stderr
  line, for example `flywheel capture: turn not recorded
  (SERVER_PROOF_FAILED). Run: flywheel traces doctor`. Claude Code shows it
  as a hook error.
- Claude Code prompt hook and every Codex hook: exit 0 with the same text in
  `systemMessage`.
- An event over 16 MiB or one that is not a JSON object fails with
  `EVENT_UNREADABLE`, and a prompt event with no prompt field with
  `PROMPT_MISSING`: the hook never commits to an empty prompt it did not
  read.
- No hook exits 2, so capture never blocks your work.
- Each failure leaves one record under `state/capture-failures/v1/` with the
  client, event, session id, prompt key, reason code and time. It holds no
  prompt, no answer, no path and no working directory. The next prompt says
  how many captures failed; `flywheel traces doctor --ack` moves the records
  aside once you have fixed the cause.

Reason codes: `HOME_MISMATCH`, `HOME_IN_WORKTREE`, `HOME_UNRESOLVED`,
`USAGE`, `EVENT_UNREADABLE`, `PROMPT_MISSING`, `TOKEN_MISSING`,
`TOKEN_UNREADABLE`, `GATEWAY_NOT_RUNNING`, `LISTENER_MISMATCH`,
`LISTENER_NOT_OWNER`, `SERVER_PROOF_FAILED`, `HELLO_RATE_LIMITED`,
`GATEWAY_UNREACHABLE`, `TIMEOUT`, `AUTH_REFUSED`,
`REQUEST_REJECTED:<status>`, `GATEWAY_ERROR:<status>`,
`REMOTE_NOT_SUPPORTED`.

## Switching capture off

`FLYWHEEL_CAPTURE=off` makes the hook contact no gateway. The first event of
each session shows "Flywheel capture is off here (FLYWHEEL_CAPTURE=off in
<working directory>). This session is not recorded." Every suppressed event
leaves one record with the client, the time and the session id; on Windows
the record also keeps the working directory encrypted with your Windows
account's key, elsewhere it keeps no directory. The gateway folds new
records into the custody ledger (one count per client and project, the
project as a keyed digest) and the witness when a hook next reaches it, and
the doctor does the same and shows the counts.

## What this does not protect against

Other processes running as you can read the gateway token and speak this
protocol. The channel protects against other accounts on the machine and
against a stale or squatted port, not against your own processes. A hook
cannot report anything when the client does not run it: managed policy, an
untrusted workspace, or a mount the doctor could not read. If a client runs
hooks inside a low-integrity sandbox, the hook cannot read the token and
reports `TOKEN_UNREADABLE`.

## The old scripts

`scripts/hooks/wrapper_scaffold_hook.py` and
`scripts/hooks/wrapper_turn_receipt_hook.py` now print a deprecation line
and run the module above. They stay for one release.

## Flywheel's own hook registry

Flywheel's accountable hook registry is separate from client mounts.
`POST /api/hooks/register` records an argv hook under a one-use
`hook.register` gateway grant with `write` scope and does not fire hooks as
part of registration. `GET /api/hooks` is private because it returns the full
registry, including argv. `POST /api/hooks/run` fires only the sealed
registrations named in the one-use `hook.run` grant with `exec` scope. Before
dispatch, the gateway reloads the registry, refuses the grant if matching rows
changed, and executes the approved rows rather than a later registry read.
The registry is rechecked on load and run for schema, seal, and argv policy so
a tampered or shell-shaped row is refused before dispatch.
