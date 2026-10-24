# Changelog

Release notes for each version live in `RELEASE-NOTES-<version>.md`. This file
lists the changes in each release with the pull request that made them.

## Unreleased

Scope field (migration from `does_not_prove`)
- Every record names what its result covers in a `scope` field, in plain positive words. The field replaces `does_not_prove`, whose entries were limits phrased as negatives. Each value was rewritten from what the module checks; codes such as `NOT_PROVES_EXACTNESS` became codes for the covered property, emitted when it holds (`PREDICATE_EXACT`). Certificate results carry `BOUND_FROM_SUBMITTED_OBJECT`: the verified object's value bounds the optimum from one side.
- Every schema whose records changed moved up one version: receipts to `flywheel.receipt/v5`, routed receipts to v2, QA cards to v3, and the gateway, bulletin, evidence, writing, trace and statistics records listed in `project-docs/SCOPE-MIGRATION.md`. Writers emit the new version. Readers accept both versions and read each with its own vocabulary, so v3 and v4 receipts, v1 records and every sealed or anchored artifact still verify with their original bytes.
- `harness/scope.py` (`scope_of`, `scope_list`) reads either name; the desktop app has the same helper. `scripts/check_scope_migration.py` runs in CI and keeps the older name to the readers, the sealed artifacts and historical documents. `tests/test_scope_migration.py` checks both readers, the old-version artifacts, and the bytes of 71 kept artifacts.
- Printed headings say `scope:`. Records in superstack's vendored receipt format keep their field until superstack moves.

Checks and reports
- Eval results and the harness-config hash record the serving runtime: framework, GPU, dtype, compile mode, batch shape, determinism flags and capture hooks. A rerun reports DRIFT on an output mismatch only when both runs used the same deterministic runtime. See `docs/features/eval-runtime-and-access.md`.
- Eval results record which of six access surfaces the evaluator had, and `claim_scope` rejects a claim that needs access the run did not have.
- New `coverage` and `differential` checks, and 16 partial-check false accepts added to the corpus. 15 of the 16 are caught, and 53 of 56 across the corpus, with 0 false rejects on 376 known-good items. See `docs/features/checks.md`.
- Text, Markdown, LaTeX and HTML reports print their limits under one plain heading, "limits" or "## Limits". The `--limits` help in `flywheel acp`, `dap` and `lsp` says "print the limits of a run record". The bundled `reproduce.py` says what MATCH covers.
- `audit run` runs two starter detectors: receipt integrity and unbacked claims. The detector that asked each work product for a stated limit is removed.

## 1.9.0 (2026-10-15)

Behaviour changes
- `-p` JSON results carry `harness_config_sha256`, and the ledger gains a `harness_config` entry when settings change.

Install
- Homebrew formula and Scoop manifest in this repository. (#409)

Checks and reports
- `flywheel behavior-check A B`: replay scripted sessions on two builds and report MATCH or the first diverging event. (#415)
- `flywheel report scope`: calls that reached past what was allowed, from saved session ledgers. (#413)
- A harness-config hash on every turn. (#412)
- Offline recheck of a swarm fan-in receipt. (#411)
- Footprint and startup suite, and a gated A/B runner for startup changes. (#414, #416)

Docs
- Configuration, troubleshooting, and versions and compatibility pages; a test that a 1.6.0 session still resumes. (#408)

## 1.8.0 (2026-10-15)

Behaviour changes
- `flywheel doctor` counts provider keys in the OS credential store, by name.
- `remember` is a memory permission class: refused in plan, allowed in edit and auto, asks in ask.

Connect and reach
- `flywheel setup` stores a provider key in the OS credential store. (#398)
- Azure OpenAI, Amazon Bedrock and Google Vertex AI backends. (#399)
- `flywheel update --apply` and an opt-in weekly update check. (#404)

flywheel code
- `web_search` (SearXNG, Brave, or DuckDuckGo with no key). (#400)
- Parallel read-only subagents through `tasks`. (#401)
- Plugin marketplaces and `install NAME@MARKETPLACE`. (#402)
- Background jobs stream and stop on Linux and macOS. (#403)
- PermissionRequest, PreCompact, PostCompact, SubagentStart and SubagentStop hooks. (#405)
- Project memory notes, `/memory`, `/forget`. (#406)

## 1.7.0 (2026-10-15)

Behaviour changes
- Long `flywheel code` sessions fold automatically past `--compact-budget` (default about 60,000 estimated tokens; 0 is off).
- `sandboxed_run` takes `cancel` and `work_hook`; the Windows low-integrity runner waits in slices when cancellable.

flywheel code
- Automatic compaction, `@path` mentions, `/context`, `/compact`.
- Subagents from Markdown files and a `task` tool.
- `flywheel mcp login` and `logout`: OAuth for HTTP MCP servers.
- Background jobs: `run_background`, `processes`, `/jobs`.
- Plugins: `flywheel plugin install | list | remove`.

Reach
- The repository is a GitHub Action, with an end-to-end smoke against a stub model.
- One-line installers (`install.sh`, `install.ps1`) and a three-OS first-run check in CI.
- A VS Code extension, packaged as a `.vsix` with the standard library.
- A docs site built from the repository and published to GitHub Pages; `docs/LICENSING.md`.
- Package metadata for PyPI. (#388)

## 1.6.0 (2026-10-15)

Behaviour changes
- The installed `flywheel` command enters through `cli_entry.console_main`: an unhandled exception writes a local crash report under the Flywheel home and exits 70. `FLYWHEEL_DEBUG=1` shows the traceback instead. (#382)
- `--help` on gate, up, lanes, loop-status, down, corpus-export and why prints usage and runs nothing; `flywheel gate --help` used to run the gate. (#382)
- Hosted backends put the provider's token counts on the response as `x_token_usage`; the word-count `usage` field is unchanged. (#384)

flywheel code
- `flywheel code`: an interactive coding session in the base install, on the gated loop, with `-p` for one request. (#383)
- Permission modes plan, ask, edit and auto, and `.flywheel/permissions.json` allow and deny rules. (#383, #384)
- `/undo` checkpoints; sessions saved after every turn with `--continue`, `--resume` and `--sessions`, refused when the chain, head or conversation does not verify. (#384)
- Project instructions (AGENTS.md, CLAUDE.md, FLYWHEEL.md) and `/init`; `todo` tool; plan-mode prompt; `/cost` with provider-reported tokens; `--output-format json|stream-json`. (#383, #384)
- MCP servers from `.mcp.json`-shaped files and `flywheel mcp list|add|remove`; Claude Code format hooks; Markdown custom commands; Agent Skills; `web_fetch`. (#384)
- `--acp`: Flywheel as an Agent Client Protocol agent for editors. (#384)
- `--worktree NAME` and `--plain`. (#385)
- Commands in a session run in the OS sandbox with a scratch TEMP and HOME, so `python -m pytest` runs there. (#383)

Install and support
- `flywheel doctor`, `flywheel update`, local crash reports, issue templates and SUPPORT.md; README and GETTING-STARTED name the current release. (#382)
- Trace inventory lists code sessions (S25) and crash reports (S26). (#382, #384)

Other
- The explainer and README show the 1.5.1 release films. (#379)
- The ablation runner refuses a criterion run that gives no readable verdict. (#380)
- The 1.1.2 release notes cite GHSA-g5gv-7893-ff5c. (#381)

## 1.5.1 (2026-10-14)

No runtime change; the Python package changes only in its version number.

Release media
- Each published release renders two captioned videos from its own files and attaches them: a walkthrough of the Form 1040 output check (FAIL exit 1, PASS exit 0, UNVERIFIABLE exit 3) and an explainer of why the tax table, not the rate schedule, decides the answer. Every number on screen is read from the release checkout at render time. `.github/workflows/release-media.yml` calls raw-native's media workflow, which renders on a hosted runner with a software GPU adapter. (#377)

Docs
- An animated explainer page, `docs/explainer/index.html`: the run lifecycle, the shell capability check on seven commands, a sealed `flywheel gate` result and its recheck, and the stage receipt chain, with every value taken from a run of the repository. (#375)
- README Watch and Walkthrough sections. (#376)

## 1.5.0 (2026-10-04)

Behaviour changes
- A math-domain `PASS` now needs two agreeing kernels. After the Lean kernel accepts the compile and leanchecker replays it, nanoda (an independent kernel sharing no code) type-checks the exported declarations; a `PASS` reads `kernels_agreeing: 2`, the kernels disagreeing is `FAIL`, and a missing or unusable second kernel is `UNVERIFIABLE`. `LeanOracle.output_hash` folds in `kernels_agreeing`, so older receipts' output hashes differ for the same candidate. (#370)
- The separate-identity signer anchors its heads by default: setup installs a 15-minute anchor timer, and `flywheel monitor verify --anchors` holds the store to every anchored head with new findings `ANCHORED_HEAD_DISAGREES`, `STORE_SHORTER_THAN_ANCHORED_HEAD`, `ANCHOR_RECEIPT_INVALID` and `ANCHORED_HEAD_WITHOUT_RECEIPT`. `--no-anchor` opts out. No signer is installed on any known machine, so nothing is anchored yet. (#371)

Monitor admission gate
- `flywheel monitor gate <adapter>` runs a text monitor over a frozen, hash-pinned set of 2,676 parity-product items: 892 known-invisible items from the 2026-10-04 control bank, where the computation happened with nothing in the trace and a NO is false assurance, 892 known-visible items generated from a fixed seed, where the full working is in the trace and the correct verdict is NO, and 892 known-visible parity items from a second seed, where the trace shows the parity check and the correct verdict is YES. It reports the false-assurance, false-alarm and missed-check rates with Wilson 95% intervals and the UNVERIFIABLE rate, and admits a monitor only when all three upper bounds sit under the preregistered bars (0.0100, 0.0500 and 0.0500). Six planted controls (always-YES, always-NO, always-UNVERIFIABLE, random, a shortcut that says NO whenever the trace shows arithmetic, and an oracle) run on every gate run; if one lands off its expected outcome the gate reports itself UNVERIFIABLE. The result is a `flywheel.receipt/v4`, optionally signed, that `flywheel monitor gate-verify` re-derives from the records before it checks the signature. See `docs/MONITOR-GATE.md`.


Verification
- A second Lean kernel re-checks bound proofs: the compiled module is exported with lean4export and type-checked by nanoda, which permits only `propext`, `Classical.choice` and `Quot.sound`. Receipts add `external_kernel` (tool, version, source commit, binary sha256, licence, exporter, verdict, statement hash). Two agreeing kernels rule out a bug in either kernel alone, not a shared fault, and `spec_fidelity` stays `UNVERIFIED`. See `docs/PROOF-AND-FORMATS.md`. (#370)

Preregistration and anchoring
- `python -m harness.signer anchor` signs each store's head, logs its SHA-512 and an Ed25519ph signature in Rekor and submits its SHA-256 to OpenTimestamps; only hashes, a signature and the public key leave the machine. False-success control: a host attacker who rechains and re-signs with the real key reads `MATCH` under the key alone and `DRIFT` against the anchored head. See `docs/features/rekor-anchor.md`. (#371)

Docs and rechecks
- The signer's threat model is written down: the guarantee rests on the OS identity boundary and the host kernel and hypervisor; root or SYSTEM can read the key or sign a replacement history, and an anchored head bounds that. See `docs/SEPARATE-SIGNER.md`. (#369)
- `handoff/site-designer/MANIFEST.sha256` resealed to the LF blob digest of `evidence/benchmark-ci.json` (the file never changed; the recorded value was the CRLF-form digest), with a dated correction and `RESEAL.md`. (#372)
- CI rechecks every `docs/art/receipts.json` digest against its stored SVG, so regenerating an SVG without updating the receipt now fails. A match shows the bytes are the ones the receipt names, not that the scene and seed produced them. (#373)
## 1.4.0 (2026-10-04)

Behaviour changes
- Tool-call receipts with no `authority` field verify as `FINDING` (`NO_AUTHORITY_RECORDED`) under the new authority check, and every receipt written before this release has none. `verify_receipt` is unchanged. (#361)
- `flywheel monitor verify` exits 3 with `UNANCHORED` when no trust root is pinned, where it used to report `MATCH` and exit 0. The old result stays in the report as `internal_verdict`. (#359)
- A Lean proof that does not match its task's pinned statement fails; a task with no pinned statement is `UNVERIFIABLE`. See Verification below. (#365)

Pre-action monitor
- A separate-identity signer: runs as its own OS user or account, holds a key the agent cannot read, signs each record's sequence number, previous seal and seal once, puts the OS-reported caller identity inside the signed bytes, and fails closed. A CI job runs it as a second Linux user. See `docs/SEPARATE-SIGNER.md`. (#359)
- An `authority` field on tool-call receipts (`intent`, `policy:machine`, `scope`, `policy:self`, `none`), re-derived by the verifier; `policy:machine` counts only when signed by a pinned separate-identity signer. See `docs/ACTION-AUTHORITY.md`. (#361)
- The rule pack is unchanged; digest `a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4`.

Verification
- The math domain oracle now binds a Lean proof to the statement its task pinned. Before, `LeanOracle.verify` never read its task, so any closed theorem passed, `theorem unrelated : True := trivial` included (disclosed in `project-docs/records/2026-09-23-lean-oracle-task-binding.md` and the 1.0.3 limits). A task pins `challenge` (theorem name, statement, optional header); without one the verdict is `UNVERIFIABLE` with reason `SPECIFICATION_UNPINNED`. The candidate compiles once; a Lean program reads the compiled module as data, requires the pinned theorem's exact elaborated type and identical definitions behind it, and walks its axioms from the artifact; leanchecker replays the same module. Receipts (`flywheel.lean-receipt/v2`) add `statement_sha256`, `challenge`, `binding`, `trusted_base`, `artifact_sha256` and `spec_fidelity: UNVERIFIED`. Unrelated, weakened, renamed, shadowed-definition, shadowed-instance, `prelude`, `sorry`, custom-axiom, metaprogram-axiom and kernel-skip probes are all refused against a real kernel; the real proof passes. Behaviour change: a proof of anything other than the pinned statement now fails, and math claims through paths that pin no statement read `UNVERIFIABLE` where they read `PASS`. No published receipt depended on the hole. See `docs/PROOF-AND-FORMATS.md`. (#365)

Preregistration and anchoring
- `artifacts/prereg/signed-head.json` now signs the whole eight-entry log; the original one-entry head is kept at `heads/head-0001.json`, and CI fails when the signed head and the log disagree. (#358)
- `flywheel anchor head` and `flywheel anchor verify`: log a signed head in Sigstore Rekor (Ed25519ph, hashes only) beside OpenTimestamps, and recheck both offline against pinned keys; `--online` adds a consistency proof. The size-8 prereg head is at Rekor index 3077414145. See `docs/features/rekor-anchor.md`. (#366)
- A preregistered placebo test for exact Shapley attribution: `qwen2.5:7b` credited 0 of 80 controls (Wilson 95% 0.000 to 0.046); an exploratory `qwen2.5:0.5b` run credited 7 of 80. See `docs/features/shapley-placebo.md`. (#357)

Rechecks and canonical bytes
- `.gitattributes` defaults text to LF on every platform, so a Windows clone hashes to the stored bytes. `harness/canonical_bytes.py` reports `EOL_ONLY` (exit 3) when only line endings differ; `python -m harness.prereg_pins` checks a preregistration's file pins. See `docs/CANONICAL-BYTES.md`. (#363)
- `RECHECK.md` and `python -m harness.recheck run`: one-command recheck manifests with a control that must fail; seven manifests in `recheck/`, CPU ones run in CI on Linux and Windows. The METR evidence verifier reports `INSPECT_INPUT_BUSY` for a transient Windows sharing refusal instead of a false rejection. (#363)
- The site-designer handoff and the Inspect fixtures are pinned to committed bytes, with a `canonical-bytes` workflow on Linux and Windows. (#364)

Receipts
- A signed result receipt for an approved PySyft job, with a stdlib verifier and 16 paired tamper tests. See `docs/features/pysyft-result-receipt.md`. (#356)

Docs
- README header, hero art and brand assets. (#360)

## 1.3.4

Windows app
- The 1.3.3 Windows installer was not published. Its build stopped at the frozen engine check: `/api/lanes` failed in the frozen engine, and the check reported `RELAY_ROSTER_HTTP`. The lane roster imports the raw lane's adapter by its registry name, and the freeze left that module out because PyInstaller cannot follow a name in a string. The Windows app shows its lanes from the same roster, so the 1.3.3 app could not have listed them. The freeze now adds every adapter-lane module named in the lane registry, and a test in pull-request CI fails when one is missing. The 1.3.3 wheel on PyPI was not affected: a pip install imports the adapter from source. (#355)

## 1.3.3

Lanes
- `raw`, a reference renderer lane: raw-native 0.5.0 renders on the CPU and checks its screen-space AO against a ray-traced reference. Install fetches the release binary by URL and refuses it unless `SHA256SUMS` and the pinned binary digest match. Three rechecks: arithmetic from the files alone (raw-native's own `receipt.json` included), replay, and another renderer's AO against the reference. Every receipt is a superstack receipt carrying identity (MATCH or DRIFT) and tolerance (PASS, FAIL or UNVERIFIABLE). See `docs/features/raw.md`. (#353)
- The superstack contract v0.2.0 is vendored at `harness/_vendor/superstack.py`, pinned by SHA-256 and checked against its own vectors in CI. (#353)

Reliability
- Five Windows CI tests that failed and then passed on rerun are fixed at their cause: two wall-clock races, a process startup race, and the Rowan TTS server closing a connection with an unread request body (every POST now reads its body first). The desktop goldens accept host rasterizer noise within measured limits and still fail on real changes. After the fix, 11 of 11 runs of each Windows test shard and 10 of 10 Windows desktop runs passed. (#352)

## 1.3.2

Pre-action monitor
- Three HOLD rules for irreversible deletes: `destructive/004` (`find -delete`, `find -exec rm`, `shred` outside the workspace), `destructive/005` (`git clean -f`) and `destructive/006` (remote repository, release, bucket and cloud-resource deletes). The rule-pack digest changes; re-pin `expected_rules_digest`. (#347)
- Costly-relief scenario beside the false-accept corpus: 93 irreversible actions offered with an incentive, each with a no-incentive twin, and 45 reversible look-alikes. Before the new rules 36 of 93 offers passed; now 93 of 93 are held, and incentive text changed no verdict before or after. See `project-docs/records/costly-relief/RESULT.md`. (#347)
- Typed judge mode: a SystemOne endpoint (such as Clef-flash) answers four narrow yes/no questions, code combines them into ACT, ABSTAIN or ESCALATE, and the monitor holds on ABSTAIN (`judge_abstained`) and ESCALATE. Default for `protocol: systemone`; met every pre-stated bar on a held-out half of 788 labelled agent actions (hold precision 0.748 [0.661, 0.818], recall 0.835 [0.752, 0.894]). See `docs/PREACTION-JUDGE-TYPED.md`. (#342)
- Typed override reasons and a later outcome check for monitor holds; the two-coder agreement bar is not yet measured. See `docs/PREACTION-OVERRIDES.md`. (#344)

Verification
- `flywheel verify-share`: size-weighted share of shipped output by check route per week, a flag when the unchecked share rises two weeks running while output grows, and a cost-to-verify meter per task family. On 832 merged PRs no week was flagged, so its usefulness bar is not met. See `docs/VERIFICATION-SHARE.md`. (#346)

Search
- `--effort-gate off|first-pass|sequential`, off by default. On hard_v2 (n = 110), `sequential` kept 7 of 7 problems of search's gain at 0.446 [0.391, 0.502] of the samples and met the pre-registered bar; `first-pass` drew 0.509 and missed by 0.009. See `docs/features/search-selection.md`. (#349)
- Cost receipts: each candidate's measured time beside the hardware's speed-of-light floor, opt-in per arm. On 600 calls of a local 14B model on one RTX 4090: 600 receipts, 0 below the floor, median ratio 1.33. See `docs/features/cost-receipts.md`. (#350)

## 1.3.1

Usage
- Live counter charts for a selected local llama.cpp or vLLM runtime on the desktop Usage screen, read through the authenticated `/api/usage/live` route from loopback addresses only; the status line is a screen-reader live region. (#309)

Search and checks
- One library of deterministic checks (schema, AST, state machine, value on page, recompute) with one call and one receipt, used by search as candidate pre-checks and by the pre-action monitor as a layer-0 gate; catches 38 of a 40-item false-accept corpus with 0 false rejects on 353 known-good items. See `docs/features/checks.md`. (#343)

Native provider sessions (preview)
- Persistent, resumable, approval-gated Codex and Claude sessions inside the gateway operation, grant and trace path; desktop `native` chat mode; managed Codex gateway flags; `MODEL_SELECTION_REQUIRED` for `codex-cli` without a model; `--strict-bind`; Tailscale address lookup for the mobile launcher; `state/codex-managed-policy` registered in the trace inventory. (#282)

Integrations
- The Claude Code mod is licensed `FSL-1.1-MIT` with its own LICENSE file; audit fixtures renamed to `forged-consent-sample` and `permissive-policy-sample`. (#341)

## 1.3.0

Pre-action monitor
- Hold model-API requests that ask a provider to fetch a web page, including encoded bodies, script files and provider-side search tools (`egress/003`); hold reads of inference credential files (`credential/001`). (#326)
- Optional rule `scope-escape/004` for side-effecting tool names, off by default; turn on with `monitor.optional_rules`. (#327)
- `flywheel monitor owner` prints `installed_rules_digest`; docs cover re-pinning, single-agent scope and known limits. (#336)

Search and evaluation
- Search mode: the visible tests pick a candidate and the hidden tests decide on it; runs without hidden tests are labeled self-scored. `best_of_k` needs a held-out scorer or `self_scored=True`. (#328)
- Opt-in duplicate pruning, `--prune-duplicates M`. (#332)
- Held-out rerun of the shipped hard benchmark. (#337)
- Report-only red check on pull requests. (#324)
- Read-only evaluation result admission guard for offline evaluation consumers. (#311)

Re-derivation and receipts
- Replay certificate for seeded solvers. (#329)
- `flywheel rederive`, a re-derivation gate with a standard-error luck margin (preview). (#333)
- Routed receipts: which lane produced a result, bound into a signed digest. (#331)
- Findings report scores between a trivial baseline and a ceiling. (#330)

Scoring
- Honest exit outcome with an `exit_price` setting, default 0. (#334)

Integrations
- Claude Code mod under `integrations/claude-code-mod/`, experimental. (#335)
- The mod runs on Claude Code 2.1.286 and installs from the Flywheel plugin marketplace as `flywheel-mod@flywheel-skills`; the wheel now ships the monitor's rule pack `harness/preaction/rules_v1.json`. (#339)

Canon
- Rules of record under `docs/rules/`: evidence and useful work, evaluation that informs decisions, neutral evaluation, compete to win, environment attribution and voice, just culture, the commons, threat-informed defense, coordinated disclosure, conflict transparency and research synthesis; credo additions. (#338)

Gateway
- Static serving rejects hidden paths and unsupported file types and resolves directory indexes before the containment check; malformed chat `temperature`, `max_tokens` and `seed` return a structured 400. (#310)
