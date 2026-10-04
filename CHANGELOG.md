# Changelog

Release notes for each version live in `RELEASE-NOTES-<version>.md`. This file
lists the changes in each release with the pull request that made them.

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
