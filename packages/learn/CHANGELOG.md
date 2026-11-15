# Changelog

## Unreleased

- Licence, 2026-10-23: the code moves from the Fair Source licence to the GNU Affero General Public License, version 3 only (AGPL-3.0-only), on the author's decision of that date. Every commit in the history is the author's own. Version 2.3.0 and every earlier release, on npm and as GitHub tags, keep the Fair Source licence; AGPL-3.0-only applies from the next release. `LICENSE`, `license` in `package.json` and `package-lock.json`, the README and the explainer page change with it. AGPL-3.0 allows no extra restrictions, so the old integrity clause (graded assessments always halt for the human) stops being a licence term and stays a design commitment that `doctor` checks.
- README and docs introduction rewritten to open with what learn does and a command to run, with
  a shorter feature list and a short "Things to know" section. The npm description matches.

## 2.3.0, 2026-10-03

- Choice items (`learn-choice/1`, `src/tutor/choice.mjs`). A recall question keys one answer and names the misconception behind each wrong choice. `diagnoseChoice()` tells a wrong attempt which misconception it matches, using the same top levels as the arithmetic tree, and never returns the keyed answer. `doctor` checks that with a probe and a known-bad item.
- A browser entry, `@harperz9/learn/browser` (`src/browser.mjs`). Practice, scheduling and diagnosis load in a page with no bundler. The session functions moved from `tutor.mjs` into `session.mjs`, which has no Node built-ins; `tutor.mjs` re-exports them unchanged. A test walks the entry's import graph and fails on any `node:` or bare import.
- An attempt may carry a `misconception` leaf, and `misconceptions()` counts it.

## 2.2.0, 2026-10-03

- Misconception diagnosis for arithmetic practice. A wrong answer to a whole-number or fraction-addition prompt walks a fixed tree of yes-or-no questions and gets a cause, such as `misrecruited.no_carry` or `slip.one_digit`. `tutor misconceptions` and `learn_tutor_misconceptions` now count causes per objective in a `diagnoses` field. The diagnosis never shows the correct answer. On 50 held-out teacher-labelled answers it agreed with the teacher on 96%; details in `docs/MISCONCEPTION-DIAGNOSIS.md`.

## 2.1.0

- Add Windows x64 MCPB and ZIP packages with a bundled runtime, scoped skills and qualified local stdio workflows.
- Require clean exact-tag source, versions ending in .0, payload hashes and matching same-release artifacts; refuse changed release reruns.
- Preserve the graded-assessment halt and CLI-only live course actuation; validate assessment outcomes rather than field-name substrings.

All notable changes to `learn`. Versions follow semantic versioning; each minor release was built
behind the `feat/learning-loop` branch and reviewed before merge.

## 2.0.0

A security release that also makes the package's own entry points work. It changes where learn
keeps state and how `resume` authorizes steps; "Moving from 1.6.0" below lists what to do.

### Security

Affected: 1.6.0 and earlier.

- **Path escape through `sessionId` and `runId`.** `learn_tutor_plan` joined `sessionId` into
  `tutor/<id>.json` with no check, so `"../.claude/settings"` replaced a project's
  `.claude/settings.json`. `learn_tutor_record`, `learn_verify` and `learn_receipt` read or
  rewrote files the same way, and `learn_dry_run`, `learn_tutor_prooflesson` and
  `learn_tutor_reverify` read any path, with a non-JSON file's first characters in the error.
  Ids now match `[A-Za-z0-9._-]{1,64}`, must not start with a dot or a hyphen and must not be a
  Windows device name. Every resolved path, after links and junctions, must stay inside the state
  folder. Path arguments resolve inside it, and a failure carries a closed code and fixed text. A
  path outside the folder on its text, such as a `\\host\share` UNC path, is refused before
  anything opens it, so no SMB or WebDAV connection is made. A link whose target does not exist
  is refused, not followed.
- **Resume submitted and paid without the opt-in.** `learn resume` passed
  `allowIrreversible: true` on every call. After a halt at `assess`, a plain resume clicked the
  next `submit` step and a `cost` step, and the receipt filed the submit as a witnessed automated
  submission. A resume now keeps the run's recorded mode, `--submit` takes only `manual` or
  `witnessed-auto`, and steps flagged `cost` or `irreversible` halt unless `--allow-cost` is given
  on the invocation that reaches them. The ledger entry of each step a grant allowed names it,
  and the receipt lists it (`witnessedAutoSubmissions[].authorizedBy`, `authorizedCostSteps`).
  The command line is read once, so a grant word given as the value of another flag, as in
  `--attest "--allow-cost"`, is that flag's value and grants nothing.
- **Children of `LEARN_*_CMD` inherited the caller's folder and environment.** With the documented
  `python -m crucible`, a `crucible/` package in the folder where `learn assist --crucible` ran was
  executed. Children now start through the vendored safe spawn helper 1.0.1
  (`src/_vendor/safe_spawn.mjs`, pinned in `VENDORED.sha256`): absolute executable, private empty
  folder, environment allowlist extended only by `LEARN_CHILD_ENV`,
  `NoDefaultCurrentDirectoryInExePath=1` on Windows, `-P` and `PYTHONSAFEPATH=1` for Python.
  A command given as a bare name is looked up on PATH without any entry that reaches the folder
  learn runs in: an entry naming that folder or a folder below it, a junction or symlink to it,
  or a quoted spelling of it. The child's PATH leaves those entries out too, so a peer command
  that runs a helper by bare name does not find one planted there on PATH. When learn runs in a
  filesystem root, in your home folder or in a folder above it, it skips only an entry naming
  that folder itself. It never skips Node's own folder or the Windows, System32 and SysWOW64
  folders, and when it runs in one of them it skips no entry. On Windows a drive-relative name
  such as `C:tool` is refused. For the same reason `LEARN_NATIVE_CONTROL` must be an absolute
  path: a relative value imported a `browser.mjs` from the folder where `learn run --native`
  started.
- The shipped `docs/smoke.md` no longer names a local development folder. The code default was
  already removed on `main` and ships here for the first time.

### Breaking changes

- **State location.** Sessions (`tutor/`) and runs (`runs/`) live in `LEARN_HOME` when it is set,
  else in `%LOCALAPPDATA%\learn` on Windows, `~/Library/Application Support/learn` on macOS, and
  `$XDG_DATA_HOME/learn` or `~/.local/share/learn` elsewhere. 1.6.0 wrote them into the folder the
  command started in. `learn status` prints the folder under `state`.
- **Resume.** A plain `learn resume` no longer submits or pays. `run --submit witnessed-auto` no
  longer covers `cost` steps. A completed or denied run cannot be resumed.
- **MCP errors.** A tool failure is a result with `isError: true` and `structuredContent`
  `{code, retryable, setup, detail}`, where code is `INVALID_ARGUMENT`, `NOT_FOUND`, `CONFLICT` or
  `INTERNAL`. 1.6.0 returned JSON-RPC `-32000` errors with free text. An unknown tool is `-32602`.
- **No silent overwrite.** `learn_tutor_plan` and `learn tutor plan` refuse to replace an existing
  session unless `replace: true` or `--replace` is given.
- **MCP paths.** `learn_dry_run` takes `workflow` inline or `workflowPath` inside the state
  folder; `packetPath` and `file` resolve inside it too. `learn_tutor_reverify` names each
  receipt relative to the state folder (`tutor/<id>.mastery.json`), not by its absolute path.
- **Peer commands.** A `LEARN_*_CMD` child sees only allowlisted variables and starts in a private
  folder, and a relative path in the command is refused. A peer command installed inside the
  folder learn runs in is no longer found by bare name, whether it sits in a project's
  `node_modules/.bin` or in a virtual environment inside that folder. With such a venv activated,
  `python` resolves to the next Python on PATH, so name the venv's interpreter by absolute path,
  for example `["/absolute/path/to/course/.venv/bin/python", "-m", "crucible"]`. Each peer start
  reads every PATH entry, so a slow or unreachable network folder on PATH delays every start. The
  interop functions `crucibleAssess`, `gatherRun` and `telosRender` are async; they are not
  package exports.

### Fixed

- The `learn` bin works. `src/cli.mjs` starts with `#!/usr/bin/env node`, the repository checks
  out LF everywhere (`.gitattributes`), and main-module detection compares real paths, so the bins
  npm links run. In 1.6.0 the bin printed nothing on Windows and failed on Linux.
- The human attestation records the real time of the resume. 1.6.0 recorded 1970-01-01.
- MCP `serverInfo.version` reports the package version; 1.6.0 said 1.0.0. A test now holds
  `package.json`, `package-lock.json`, `src/index.mjs`, `serverInfo`, status, doctor, this file
  and the README to one version.

### Added

- `learn mcp` and a `learn-mcp` bin start the MCP server: `npx -y @harperz9/learn@2.0.0 mcp`.
- `--dir <folder>` on the CLI for a project-local state folder, and `LEARN_HOME` for every entry
  point. `learn status` and `learn_status` report the folder in use under `state`, with its
  source: `--dir`, `LEARN_HOME` or `default`. `LEARN_*_CMD` also takes a JSON argv array, which
  keeps a path with spaces whole.
- A release workflow. On a `v*` tag it checks the tag against every version site, smokes the packed
  tarball through `npx` on Windows, Linux and macOS, publishes with npm trusted publishing (npm
  records provenance), and creates a GitHub Release with the tarball and `SHA256SUMS`. CI runs the
  same tarball smoke on every push. Actions are pinned by commit SHA.
- Also released from `main` for the first time: the repository art and its tests, and the
  `src/interop.mjs` organ-bundle entries (not exported and not imported by the package).

### Moving from 1.6.0

- To keep sessions and runs in a project folder, pass `--dir <that folder>` or set `LEARN_HOME` to
  it. To move them, copy the folder's `tutor/` and `runs/` into the folder `learn status` prints.
- A run that should submit on resume: pass `--submit witnessed-auto` on `run` or on that resume. A
  run that should pay: pass `--allow-cost` on the invocation that reaches the payment step.
- MCP clients that read JSON-RPC error text read `structuredContent.code` instead.
- `LEARN_TELOS_CMD="node ../telos/src/cli.mjs"` becomes
  `LEARN_TELOS_CMD='["node", "/absolute/path/to/telos/src/cli.mjs"]'`. Name any variable a peer CLI
  needs in `LEARN_CHILD_ENV`, for example `LEARN_CHILD_ENV=ANTHROPIC_API_KEY`.

## 1.6.0

The derive-schedule entry below shipped in the published 1.6.0 package. Earlier copies of this
file listed it under Unreleased.

- `tutor/fsrsderive.mjs`: make the FSRS schedule a **re-derivable function of the witnessed graded
  attempt log**. `deriveItemStates(attempts)` replays the recorded scored attempts (each carries its
  `grade` + `timestamp`) through the same pure `gradeAttempt()` math the live scheduler uses, so it
  reconstructs `session.itemState` bit-for-bit from `session.attempts` alone (proven by a parity test
  against the live state). `deriveScheduleReceipt(session)` audits the cached hint against that clean
  replay and emits a `MATCH` / `DRIFT` / `NO_FSRS_LOG` verdict plus a hash-chained ledger over the
  graded attempts; the log-derived state is authoritative, so a stale or tampered cache is flagged as
  `DRIFT` with a per-field diff rather than trusted. `optimizeParameters(attempts)` adds an *advisory*
  per-learner fit: one initial-difficulty prior per objective, fitted from that learner's own accuracy
  (a documented heuristic prior, not a full FSRS weight optimization); it never moves the audit
  verdict or the mastery gate. Wired into the CLI (`tutor derive-schedule <id> [--optimize]`, writes
  `tutor/<id>.derive-schedule.json`, non-zero exit on DRIFT) and MCP (`learn_tutor_derive_schedule`,
  `optimize`). A new `doctor` invariant `tutor.schedule_rederivable_from_log` proves the audit can
  FAIL: a clean session re-derives to MATCH and a tampered cache is caught as DRIFT. INTEGRITY
  unchanged: `fsrsderive.mjs` is pure, never calls `Date.now()`, never grades, never appends to
  `session.attempts`, and never feeds the mastery gate: `itemState` stays a hint, the witnessed log
  stays the truth. Backward compatible: all prior tests pass; 14 new tests across
  `learn-fsrs-derive.test.mjs` (10) and `learn-fsrs-derive-cli.test.mjs` (4).

- `tutor/fsrs.mjs` + `tutor/itemscheduler.mjs`: opt-in FSRS-class adaptive memory model.
  Per-item *difficulty* / *stability* / *retrievability* with a user-set retention target, so the
  scheduler decays each item on its own forgetting curve and next-selects the item you are most
  likely to have forgotten (retrievability-ranked), rather than re-surfacing whole objectives on a
  fixed Leitner ladder. `fsrs.mjs` is pure math (no I/O, no `Date.now()` â€” `now` is always
  injected); `itemscheduler.mjs` owns the derived `session.itemState` and self-heals corrupt or
  missing state on BOTH the ranking/read path (`sortByRetrievability`/`selectNextItem`) and the
  grading/write path (`recordAttemptWithGrade` heals before grading), so a nonsensical interval can
  never reach a learner and a corrupt stored stability can never contaminate the grade math. Enabled per session:
  `newSessionWithFSRS` / `tutor.recordAttemptWithGrade` (grades 0-4), and threaded behind a
  default-false `useFSRS` flag through `schedule.reviewState`/`due` and `study.studyPlan`/
  `studyReceipt`. Wired into the CLI (`plan --enable-fsrs`, `record --grade/--now`, `study` /
  `study-receipt` / `due --use-fsrs/--desired-retention`) and MCP (`enableFsrs`, `grade`, `now`,
  `useFsrs`, `desiredRetention`). INTEGRITY: the mastery-gate still reads `session.attempts` only â€”
  `itemState` is a scheduling hint, never a verdict â€” proven by `learn-fsrs-isolation.test.mjs`
  (corrupt/delete itemState, mastery and study-receipt unchanged). Fully backward compatible: all
  prior tests pass unchanged, `useFSRS` defaults false, and the flags fall back to the Leitner/
  interleave path on legacy sessions with no `itemState`.
- `tutor/prooflesson.mjs` + `tutor/prooflessonverify.mjs`: proof-packet -> lesson. `proofLesson`
  consumes a proof-surface-style packet JSON (`version`, `packet_id`, `claim`, `scope`,
  `sources[{ref,sha256}]`, `verdicts.overall`; unknown wedge-specific blocks are treated as
  opaque) and derives a lesson that preserves the packet's own evidence surface: source refs
  (never bodies), the claim, the packet's verdict, an explanation scaffold (numbered prompts for
  the learner to derive the reasoning; the packet's decision reasoning is never dumped),
  retrieval-practice questions derived from the packet's own fields (including "what evidence
  would falsify this claim"), and a verifier binding (verdict + packet_id + source hashes). The
  lesson verdict is copied from the packet and from nowhere else; the derived lesson is frozen,
  so a lesson claiming MATCH from a DRIFT packet is impossible by construction, and a forged
  verdict enum is rejected up front.
- `misconceptionFromPacket`: for DRIFT / UNVERIFIABLE packets, a typed misconception record
  (`packet_id`, `verdict`, `misconception_class`: `contradicted` for DRIFT, `overclaim` for
  UNVERIFIABLE with recorded sources, `missing_evidence` for UNVERIFIABLE without) whose prompt
  asks the learner WHY the proof attempt failed; a MATCH packet yields none.
- `proofLessonReceipt`: the lesson receipt hash-chains a packet binding, one entry per source
  ref+hash, and the canonical lesson digest through the existing ledger machinery, and
  `learn tutor reverify` covers it: a tampered entry is `CHAIN_BROKEN`, a flipped verdict or
  edited lesson body is `VERDICT_MISMATCH`, and a chainless or illegal-enum receipt is
  `UNVERIFIED`, never verified.
- CLI: `learn tutor prooflesson <id> --packet <packet.json>` writes
  `tutor/<id>.prooflesson.json` and exits 1 on a rejected packet, writing nothing.
- MCP: `learn_tutor_prooflesson` (advisory, read-only; derives the lesson + misconception from an
  inline packet or a packet file, writes nothing).
- `doctor` gains `tutor.prooflesson_rejects_known_bad`: a clean packet must derive and re-verify,
  and each known-bad input must be rejected (forged verdict enum, tampered chain entry, verdict
  flipped MATCH-from-DRIFT, chainless receipt).
- `tutor/reverify.mjs`: tutor-receipt re-verification with typed failure codes. `reverifyReceipt`
  recomputes a receipt's own evidence instead of trusting its stored booleans (`verified` /
  `ledgerVerified` are author-controlled and deliberately ignored): the hash chain over the
  witnessed practice entries must recompute (a break is typed `CHAIN_BROKEN` with the offending
  entry's seq and hash; a hash-consistent truncation is caught by attempt accounting) and the
  stored mastery verdict must re-derive from the recorded attempts under the recorded policy (a
  divergence is typed `VERDICT_MISMATCH` with both projections). A chainless receipt re-verifies
  as `UNVERIFIED`, never as verified. A clean re-check carries a witnessed summary digest.
- CLI: `learn tutor reverify <id> [--file <receipt.json>]` exits 0 only when every checked receipt
  re-verifies as VERIFIED; any typed failure or UNVERIFIED receipt exits 1.
- MCP: `learn_tutor_reverify` (advisory, read-only).
- `doctor` gains `tutor.reverify_rejects_known_bad`: the re-verifier must pass a clean receipt and
  reject each known-bad fixture (tampered chain entry, hand-edited verdict, chainless receipt).
  A verifier that cannot fail on a known-bad input is not a verifier.

## 1.5.0

The learning loop reaches its first complete shape: every planned teach-you capability is shipped
behind the mastery-gate, and the pieces compose into one orchestrator instead of standing alone.

- `tutor/study.mjs`: the study orchestrator. Composes `due` (spaced repetition), `misconceptions`
  (ranked aggregation), an interleaved practice order, prerequisite readiness (from the concept
  map), and the mastery-gate verdict into one `studyPlan`; `studyReceipt` wraps the same plan in a
  witnessed, hash-chained receipt.
- CLI: `learn tutor study <id> --now <iso>` and `learn tutor study-receipt <id> --now <iso>`.
- MCP: `learn_tutor_studyplan` and `learn_tutor_misconceptions` (advisory, read-only).
- `doctor` gains a check that a study-receipt composition never lets a render, a visualization, or
  a pending prediction move the mastery needle.

## 1.4.0

- `tutor/predict.mjs`: predict-then-observe. `recordPrediction` records the operator's own
  prediction as a pending attempt (`correct: null`) before any observation; `scorePrediction`
  grades it afterward against what the operator actually saw. A pending prediction is never
  silently read as correct by `mastery()`.
- `tutor/map.mjs`: concept map. Normalizes objectives given as plain strings or as
  `{id, text, requires}`, computes a topological `learningPath`, and gates each objective's
  readiness on its prerequisites' mastery.
- CLI: `learn tutor predict`, `learn tutor score`, `learn tutor path`.
- `interop/telos.mjs`: the visualization bridge (`toTelosSceneSpec`, `telosRender`,
  `toAidLedgerEntry`). Concepts render as witnessed AID visualizations through the telos engine
  over `LEARN_TELOS_CMD`, fail-closed when the engine is not configured, and are recorded in the
  study log as mastery-independent (`recordVisualization`).
- CLI: `learn visualize <concept.json>`. MCP: `learn_visualize_dry_run` (advisory; renders
  nothing, returns only the scene-spec request).
- Receipt: adds an `aidVisualizations` section, structurally separate from
  `humanAssessments` / `manualSubmissions` / `witnessedAutoSubmissions`.
- `doctor` gains `telos.render_fail_closed`, `receipt.aid_never_graded`, and
  `tutor.mastery_render_visualization_independent` checks.
- fix: corrected the README test count (37 -> 67 at the time) and hardened the
  `aid_never_graded` doctor check against a receipt that silently promoted an aid render.
- chore: scoped the npm package name to `@harperz9/learn` (the bare name was taken); gitignored
  the SDD scratch directory before publishing.

## 1.3.0

The tutor layer: the teach-you engine and its mastery-gate, plus the first two learning-loop
capabilities.

- `tutor/tutor.mjs`: `newSession`, `recordAttempt`, `mastery`, `masteryReceipt`. A session tracks
  objectives and practice attempts; `mastery()` reports per-objective and overall readiness from
  accuracy and attempt-count thresholds, computed only from recorded attempts.
- `tutor/schedule.mjs`: spaced repetition (SM-2-lite / Leitner ladder) over the practice log;
  `due()` reports objectives due for review, most-overdue first.
- `tutor/misconception.mjs`: aggregates wrong attempts and the operator's own feedback per
  objective, ranked by count.
- `tutor/retrieval.mjs`: `clozePrompts` turns the operator's own assist-extracted claims into
  blanked recall prompts carrying a source; `interleave` gives a deterministic (seeded, no
  `Math.random`) mixed study order.
- `tutor/explain.mjs`: self-explanation grading. Wraps the operator's own explanation into a
  crucible thesis and buckets its claims' verdicts into grounded / shaky / unverifiable.
- CLI: `learn tutor <plan|record|mastery|receipt|due|misconceptions|retrieval|explain>`.
- MCP: `learn_tutor_plan`, `learn_tutor_record`, `learn_tutor_mastery`, `learn_tutor_due` added to
  the advisory tool set.
- `doctor` gains `gate.assess_never_allow` extended coverage and the mastery-gate falsifiable
  tests: a session with a mastered practice log stays ready regardless of what else is attached to
  it, and a session below threshold is never reported ready.

## 1.0.0

Flagship parity: the credential-logistics engine reaches its first complete, tested shape.

- `accountability/`: `witness` (content-addressed hashing), `ledger` (hash-chained, tamper-evident
  append log), `gate` (default-deny step admission; `assess` always resolves to `needs-human`).
- `workflow/`: declarative step schema, load + seal.
- `runtime/runner.mjs`: gate -> actuate -> witness -> verify -> ledger, with halt/resume.
- `actuation/`: `FakeDriver` (offline/deterministic) and `NativeDriver` (real browser via
  native-control), selected by `--native` on the CLI.
- `adapters/`: `fake`, `generic` (config-driven), and an LMS pack: Coursera, Udemy, LinkedIn
  Learning, edX, Credly, then Microsoft Learn, NonprofitReady, and a generic self-paced adapter.
- `receipt/`: dual-plus format (JSON + Markdown + HTML) separating automated logistics from human
  assessment.
- `assist/`: turns the operator's own draft into a crucible thesis (claims -> verdicts) and a
  gather manifest (sources -> receipts); authors nothing.
- Submission modes: `manual` (engine halts at each submit) and `witnessed-auto` (engine performs
  the submit via actuation with operator authorization, recording a witnessed before/after
  digest); submission mode never touches `assess` steps.
- `doctor.mjs` / `status.mjs`: the operator-spine self-check (MATCH/DEGRADED, one falsifiable
  check per integrity invariant) and capability envelope.
- `mcp.mjs`: zero-dependency JSON-RPC/stdio MCP server exposing the advisory tool set
  (`learn_doctor`, `learn_status`, `learn_verify`, `learn_receipt`, `learn_dry_run`); actuation
  stays on the operator-driven CLI.
- CLI: `learn <run|resume|verify|receipt|doctor|status|assist>`.
