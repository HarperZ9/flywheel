<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/learn/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/learn/main/docs/art/hero-light.svg" alt="learn: Turn your own material into a runnable course with spaced repetition. 7 wavering traces run from the left and narrow into a bright core over a row of tick marks." width="100%">
</picture>

# learn

A study planner for the terminal and for agents over MCP. You list the objectives you are
working toward and record each practice attempt. learn tells you what is due for review, which
mistakes keep coming back, what order to practise in, and whether you have reached mastery on
each objective.

```bash
npx -y @harperz9/learn@2.3.0 tutor plan mysession --topic "derivatives" --objectives "power-rule,chain-rule"
```

It suits anyone studying for a course, an exam or a certification who is comfortable in a
terminal, and developers who want an agent to plan study sessions. learn never answers a graded
question. A second engine handles course logistics, such as opening modules and moving between
pages, and stops at every graded step for you to do yourself.

Node 20 or newer, no dependencies. Version 2.3.0 on npm is under a Fair Source licence; the
next release is AGPL-3.0-only (see [License](#license)).

## Install and first run

```bash
npm install -g @harperz9/learn@2.3.0
```

Plan a session, record one attempt, and ask what to study next:

```text
$ learn tutor plan mysession --topic "derivatives" --objectives "power-rule,chain-rule"
tutor plan mysession: 2 objective(s)

$ learn tutor record mysession --objective power-rule --prompt "d/dx x^3" --answer "3x^2" --correct true
tutor record mysession: 1 practice attempt(s)

$ learn tutor study mysession --now 2026-06-30T00:00:00Z
tutor study mysession: 1 due, 0 misconception(s), mastery not yet
  due: chain-rule
  order: power-rule, chain-rule
  readiness: power-rule:unlocked, chain-rule:unlocked
```

Record a wrong answer with a note on what went wrong, then save a record of the session and check it:

```text
$ learn tutor record mysession --objective chain-rule --prompt "d/dx sin(x^2)" --answer "cos(x^2)" --correct false --feedback "forgot inner derivative"
tutor record mysession: 2 practice attempt(s)

$ learn tutor misconceptions mysession
tutor misconceptions mysession: 1 objective(s)
  chain-rule (1x): forgot inner derivative

$ learn tutor study-receipt mysession --now 2026-06-30T00:00:00Z
tutor study-receipt mysession: verified true, mastery not yet -> tutor/mysession.study-receipt.json

$ learn tutor reverify mysession
tutor reverify mysession: VERIFIED (1 receipt(s))
```

`--now` pins the clock so these outputs repeat exactly; leave it out to use the current time.
To try it without installing, prefix any command with `npx -y @harperz9/learn@2.3.0` in place
of `learn`. `learn doctor` runs the built-in self-checks and prints `MATCH` on every line.

From a clone, the same commands run as `node src/cli.mjs`, and the examples in `examples/` (which
the npm package does not include) work as written:

```bash
git clone https://github.com/HarperZ9/learn.git
cd learn
node --test
```

### Where learn keeps your data

Sessions (`tutor/`) and runs (`runs/`) live in one state folder: `LEARN_HOME` when you set it,
otherwise `%LOCALAPPDATA%\learn` on Windows, `~/Library/Application Support/learn` on macOS, and
`$XDG_DATA_HOME/learn` or `~/.local/share/learn` elsewhere. `learn status` prints the folder under
`state`. Pass `--dir <folder>` to keep a project's sessions in a folder beside the project. Session
and run ids use letters, digits and the characters `.`, `_` and `-` (up to 64, no leading `.` or `-`), and learn
writes nothing outside the state folder. Delete a session by deleting its files there.

## How it compares

Anki, Mochi, RemNote and SuperMemo are flashcard and note apps, with a card editor, media,
device sync and a review screen. learn has none of those. It works on objectives and on attempts
you record from the command line or an agent, and it adds misconception counts per objective, a
mastery check per objective, and prerequisite ordering. Use a card app to drill a deck. Use learn
when you want a study plan you can script.

## Things to know

- You record attempts yourself, by command or through the MCP server.
- Mastery means at least three attempts on an objective and 80% correct by default. Those are
  your own prompts, so a pass is a pass on them, not on the real exam.
- The adaptive scheduler is a small FSRS-style model written for this package. It does not use
  Anki's trained FSRS parameters, and it only orders reviews; it never changes mastery.
- Live course runs need a browser-control library that is not yet published. Without it the
  course engine runs only with its offline test driver.
- Checking a self-explanation needs [Crucible](https://github.com/HarperZ9/crucible) installed
  separately. It sorts the claims in your explanation into grounded, shaky and unverifiable
  against the sources you cite.

## Features

- **One-command study plans.** `learn tutor study` combines what is due, what you keep getting
  wrong, an interleaved practice order, prerequisite readiness and the mastery result into one
  plan.
- **Spaced repetition.** An SM-2-lite/Leitner scheduler over your practice log by default.
  `tutor due` lists overdue objectives, most overdue first. `--now` pins the clock so a schedule
  repeats exactly.
- **Adaptive per-item scheduling** (opt-in). An FSRS-style scheduler tracks difficulty and
  stability per item and surfaces the one you are most likely to have forgotten, against a
  retention target you set, such as 90%. Grade each attempt 0 to 4.
- **Schedule rebuild.** `tutor derive-schedule` rebuilds the scheduler state from your attempt log
  and reports any field where the saved state differs (`DRIFT`). `--optimize` fits a starting
  difficulty to your own accuracy.
- **Retrieval practice from your own notes.** Statements in your draft become fill-in-the-blank
  prompts, each with its source so you can check your answer afterwards.
- **Misconception tracking.** Wrong attempts and your notes on them are counted per objective, so
  the next session starts with your weakest objectives.
- **Choice items.** A short recall question keys one answer and names the misconception behind
  each wrong choice. A wrong attempt is told which misconception it matches, never the keyed
  answer. See `docs/CHOICE-ITEMS.md`.
- **Runs in a browser.** `@harperz9/learn/browser` exports practice, scheduling and diagnosis with
  no Node built-ins, so a static page can import them without a bundler. The session store, CLI
  and MCP server stay Node-only.
- **Predict, then observe.** Record a prediction before you see a worked example, then score it
  against what happened. A prediction you have not scored counts for nothing.
- **Explain it back.** Your explanation of a concept is split into grounded, shaky and
  unverifiable claims (needs Crucible).
- **Prerequisites.** Objectives can declare what they require (`{id, text, requires}`). learn
  orders them and never schedules an objective before its prerequisites are passed.
- **Lessons from claim packets.** `tutor prooflesson` turns a checked-claim packet into a lesson:
  prompts to work through the reasoning yourself and recall questions drawn from the packet.
- **Session records.** `tutor study-receipt` saves the session as a hash-chained log with its
  mastery result. `tutor reverify` recomputes both and reports `VERIFIED`, `CHAIN_BROKEN`,
  `VERDICT_MISMATCH` or `UNVERIFIED`.
- **Course logistics engine.** `learn run` follows a JSON workflow through a course and stops at
  every step tagged `assess`, at sensitive fills (credentials, payment details, CAPTCHA), at
  `submit` steps unless you allow automated submission, and at steps flagged `cost` or
  `irreversible` unless you pass `--allow-cost`. It recognizes a graded page, a submit or a fee
  only when the workflow tags it, so read a workflow from someone else before you run it.
- **MCP server.** `learn mcp` serves fifteen tools over stdio. Thirteen only read; two
  (`learn_tutor_plan`, `learn_tutor_record`) write session files in your state folder.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/learn.html)
walks through a derivatives session: planning, recording attempts, the study plan, a misconception, the mastery check, the session record under two kinds of tampering, and the course workflow stopping at its graded step. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Adaptive scheduling

For the adaptive scheduler, create the session with `--enable-fsrs`, grade attempts 0 to 4, and
ask for a retention-targeted plan:

```bash
node src/cli.mjs tutor plan sess --topic "SC-900" --objectives "identity,compliance" --enable-fsrs
node src/cli.mjs tutor record sess --objective identity --grade 3 --now 2026-06-30T00:00:00Z
node src/cli.mjs tutor study sess --now 2026-07-15T00:00:00Z --use-fsrs --desired-retention 0.9
```

On a session created without `--enable-fsrs`, these flags fall back to the default Leitner
scheduler.

## A worked session

<p align="center"><img src="docs/art/study-loop.svg" alt="A study session in eight stages: objectives, due, misconceptions, order, practice, record, mastery gate, receipt. The gate reads only recorded attempts, and not-ready names the weak objectives and sends them back to practice." width="100%"></p>

Record a wrong attempt with feedback, see the plan change, then save the session record and check it:

```bash
node src/cli.mjs tutor record mysession --objective chain-rule \
  --prompt "d/dx sin(x^2)" --answer "cos(x^2)" --correct false --feedback "forgot inner derivative"
node src/cli.mjs tutor misconceptions mysession
# tutor misconceptions mysession: 1 objective(s)
#   chain-rule (1x): forgot inner derivative

node src/cli.mjs tutor study-receipt mysession --now 2026-06-30T00:00:00Z
# tutor study-receipt mysession: verified true, mastery not yet -> tutor/mysession.study-receipt.json

node src/cli.mjs tutor reverify mysession
# tutor reverify mysession: VERIFIED (1 receipt(s))
```

The misconception now moves chain-rule up the next `tutor study` plan. `tutor reverify`
recomputes the hash chain and the mastery result from the saved attempts. This is the record it
returns:

<p align="center"><img src="docs/art/reverify-record.svg" alt="The record learn returns when it re-verifies one of its own receipts, drawn one field to a row, with what comes back in each and how a reader would check it. verdict has three readings and no fourth, and it keys off recomputed evidence rather than the receipt's own claim to be verified. failures carries a typed code: a broken hash chain names the entry it broke at, and a verdict mismatch carries the stored reading against the re-derived one. reasons is filled only when the receipt cannot be checked at all. summary.entries is the hash-chained practice log the verdict is re-derived from. summary.storedReady is the verdict as written, summary.rederivedReady is the verdict recomputed from the receipt's own attempts under its own recorded policy, and a disagreement between the two is the mismatch. witness.digest is the content address of the re-check itself." width="100%"></p>

## The course engine

The second engine follows a JSON workflow through a course: navigate, open a module, stop at
the graded step.

<p align="center"><img src="docs/art/run-lane.svg" alt="A course run in eight stages: workflow, gate, actuate, witness, ledger, halt, attest, receipt. A graded step always halts, and your attestation is appended to the same hash chain as its own row." width="100%"></p>

```bash
node src/cli.mjs run examples/course.json --id run1
node src/cli.mjs resume run1 --attest "completed Quiz 1 myself"
node src/cli.mjs verify run1
node src/cli.mjs receipt run1
```

At every `assess` step it halts and waits for you, and it halts the same way at sensitive fills,
at `submit` steps and at steps flagged `cost` or `irreversible`. When you resume, your attestation
is logged with its time, next to every step the engine took. A resume keeps the
submission mode the run started with; `--submit witnessed-auto` on `run` or on a resume lets the
engine click submit, and `--allow-cost` on the invocation that reaches a cost step lets it perform
that step. Each grant is named in the ledger entry of the step it allowed. Drivers: `FakeDriver` (offline, deterministic) and `NativeDriver` (real browser over
native-control, a browser-control library that is not published). An adapter pack covers Coursera, Udemy, LinkedIn Learning, edX, Credly,
Microsoft Learn, NonprofitReady, and generic self-paced courses, with no graded logic anywhere.
See [docs/smoke.md](docs/smoke.md) for a hand-run walkthrough against a live course site.

The engine runs only the step kinds it knows. A workflow cannot add new ones: an unknown step
kind is refused and the run stops there. When you allow automated submission, the log entry for
that step stores a digest of the page at the moment of submit.

## MCP server

```bash
npx -y @harperz9/learn@2.3.0 mcp     # or `learn mcp`, or the `learn-mcp` bin
```

Serves fifteen tools over stdio JSON-RPC: `learn_doctor`, `learn_status`, `learn_verify`,
`learn_receipt`, `learn_dry_run`, `learn_tutor_plan`, `learn_tutor_record`,
`learn_tutor_mastery`, `learn_tutor_due`, `learn_tutor_studyplan`, `learn_tutor_misconceptions`,
`learn_tutor_reverify`, `learn_tutor_derive_schedule`, `learn_tutor_prooflesson`, and
`learn_visualize_dry_run`. `learn_tutor_plan` and `learn_tutor_record` write session files in the
state folder, and `learn_tutor_plan` will not replace an existing session unless you pass
`replace: true`. Every id and path argument stays inside the state folder; workflows and proof
packets can also be passed inline. A failed call returns `isError: true` with a code
(`INVALID_ARGUMENT`, `NOT_FOUND`, `CONFLICT`, `INTERNAL`) and a fixed message that never quotes a
file. The MCP server never performs a course action or answers a graded step.

## Status

- **Release:** `2.3.0` on npm as `@harperz9/learn`; commands `learn` and `learn-mcp`; Node >= 20; zero external dependencies
  (ES modules, `node:test`).
- **CLI surface:** `learn status`, `learn doctor`, `learn mcp`, `learn run/resume/verify/receipt`,
  `learn assist`, `learn visualize`, and `learn tutor <plan|record|mastery|receipt|reverify|
  prooflesson|due|misconceptions|retrieval|explain|predict|score|path|study|study-receipt|
  derive-schedule>`.
- **Tests:** 419 across the runtime, adapters, session records, tutor, telos interop, entry points
  and security fixtures. Run them with `node --test`.
- **History:** [CHANGELOG.md](CHANGELOG.md).

## Docs

- [docs/INTRODUCTION.md](docs/INTRODUCTION.md): what `learn` is, core concepts, and a
  first-ten-minutes walkthrough.
- [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md): the study loop step by step.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how both engines are built.
- [USAGE.md](USAGE.md): install and basic usage for both engines and the MCP surface.
- [docs/ENTERPRISE-READINESS.md](docs/ENTERPRISE-READINESS.md): running learn inside unattended
  agent workflows.
- [docs/smoke.md](docs/smoke.md): a hand-run test against a live course site.
- [AGENTS.md](AGENTS.md): scope, developer contract, and verification commands.
- [CONTRIBUTING.md](CONTRIBUTING.md) and [AUTHORS.md](AUTHORS.md).
- [docs/brand/README.md](docs/brand/README.md): brand assets.

Optional companion tools: [gather](https://github.com/HarperZ9/gather) collects sources and
[crucible](https://github.com/HarperZ9/crucible) checks claims for `learn assist`;
[telos](https://github.com/HarperZ9/telos) renders math and physics concepts as visual aids. Point learn at them with `LEARN_CRUCIBLE_CMD`,
`LEARN_GATHER_CMD` and `LEARN_TELOS_CMD`, each a JSON argv array such as
`["python", "-m", "crucible"]` with absolute paths for any file. Each child starts in a private
empty folder with a short environment allowlist; name any other variable it needs in
`LEARN_CHILD_ENV` (comma-separated). A bare command name is looked up on PATH without the folder
you run learn from or any folder inside it, so a tool installed there needs its absolute path.
That covers a project's `node_modules/.bin` and a virtual environment inside that folder: with
the venv activated, `python` resolves to the next Python on PATH, so name the venv's interpreter
by absolute path, for example `["/absolute/path/to/course/.venv/bin/python", "-m", "crucible"]`.
When learn runs in a filesystem root, in your home folder or in a folder above it, it skips only
an entry naming that folder itself. It never skips Node's own folder or the Windows, System32 and
SysWOW64 folders, and when it runs in one of them it skips no entry.

## License

GNU Affero General Public License, version 3 only (AGPL-3.0-only); see [LICENSE](LICENSE). You
may use, study, change and share learn. If you run a changed version as a network service, you
must offer its users the source of that version. Copyright (C) 2026 Zain Dana Harper.

Version 2.3.0 and earlier releases were published under the Fair Source licence and keep it.
AGPL-3.0-only applies from the next release.

Graded assessments always halt for the human, and `doctor` checks that they do. Under the Fair
Source licence this was a binding clause. AGPL-3.0 does not allow extra restrictions, so in this
licence it is a design commitment of the project and its releases. Treat a fork that removes it
as a different tool.

## For developers

Run the suite and the self-check before opening a PR.

```bash
node --test
node src/cli.mjs doctor
```

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle. More tools at [harperz9.github.io](https://harperz9.github.io).

## Local client packages

The 2.3.0 GitHub release includes native Windows client packages. They are attached to the
release and are not listed in any client marketplace.

### Installation

See [the client package guide](client-plugin/README.md) for scoped skills, portable MCP configuration and same-release archives.
