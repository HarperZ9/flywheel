# Changelog

Release notes for each version live in `RELEASE-NOTES-<version>.md`. This file
lists the changes in each release with the pull request that made them.

## 1.3.1

Usage
- Live counter charts for a selected local llama.cpp or vLLM runtime on the desktop Usage screen, read through the authenticated `/api/usage/live` route from loopback addresses only; the status line is a screen-reader live region. (#309)

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
