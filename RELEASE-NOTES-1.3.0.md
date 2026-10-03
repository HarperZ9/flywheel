# Flywheel 1.3.0

Flywheel can now stop an agent's risky action before it runs, show you why, and
keep a record anyone can re-check. Search mode picks an answer with the visible
tests and lets the hidden tests decide, so a result can no longer grade its own
choice.

## Try it

```
pip install -U flywheel-verify
flywheel monitor install claude-code      # or: codex
flywheel monitor owner                    # prints your config and the installed rule-pack digest
```

Re-check a claimed improvement on seeds you did not choose:

```
flywheel rederive run.json
```

Run a task in search mode and skip duplicate candidates:

```
python -m harness.cli <task-dir> --search --prune-duplicates 2
```

## Stop risky actions before they run

The pre-action monitor holds or blocks a Claude Code or Codex tool call before
the tool runs, and seals each decision in a hash chain. This is the first tagged
release that carries it.

- It holds requests that ask a model provider to fetch a web page for the
  agent. That covers requests hidden in an encoded body, in a script file the
  agent writes, or in a provider-side search tool. On our test set the monitor
  held 25 of 25 such requests (Wilson 95% interval 0.867 to 1.000). The rules
  before this change held 10 of 25. It held none of 200 ordinary calls (upper
  bound 0.019).
- It holds reads of the agent's own inference credential files, such as
  `~/.codex/auth.json` and `~/.claude.json`. It held 5 of 5 planted reads. The
  older rules held none.
- An optional rule holds tool calls whose names say they post, send, delete,
  pay or reset. It is off by default. On 48 side-effecting tool names it held 27
  (interval 0.42 to 0.69), short of our 0.80 bar, and it held none of 50
  read-only names (upper bound 0.07). Turn it on with
  `{"monitor": {"optional_rules": ["side-effect-tools"]}}` in your owner file.

## Upgrading if you run the monitor from source

The rule pack changed. If your owner file pins `expected_rules_digest`, every
call is blocked with `rules_digest_mismatch` until you update it. The shipped
rule-pack digest is:

```
7a3eb877853df959503d3b6925c042bc13fe5d9726381fabf7bd6e8b3861bd52
```

1. Run `flywheel monitor owner`. It prints `installed_rules_digest`.
2. Check that it matches the digest above.
3. Put that value in `expected_rules_digest`.

Records sealed under the old pack stay sealed and chained. `flywheel monitor
verify` reports them as unverifiable, because the new rules cannot re-derive
verdicts made under the old ones. Turning on the optional rule changes your
monitor config digest, so you pin again after that too.

## Better answers from more samples

When a task has hidden tests, search mode now picks a candidate with the visible
tests and runs the hidden tests once, on that pick. Their verdict is the result.
A task without hidden tests runs as before, and its receipt says
`selection: self-scored`.

On Flywheel's shipped hard benchmark, rerun this way with a local 14B coder,
**no accuracy uplift is claimed**:

| Set | Tasks | One attempt | Search | Difference, 95% interval |
| :-- | :-- | :-- | :-- | :-- |
| Shipped hard set | 10 | 9 passed | 9 passed | 0.000 [0.000, 0.000] |
| Larger hard set | 110 | 61 passed | 68 passed | +0.064 [-0.009, +0.136] |

Both intervals include zero. The rule for this claim was written before the run.

The run did measure what the old path got wrong. If the visible tests had both
picked and accepted, as before this release, 22 of 90 accepted answers on the
larger set would have failed the hidden tests: a share of 0.244 (interval 0.167
to 0.342).

A separate test outside Flywheel used 142 recent programming problems, one 14B
local model and 16 samples each. Picking by visible tests beat picking by the
model's own confidence by 0.106 (interval 0.056 to 0.155). It beat a single
attempt by 0.063 (0.014 to 0.106). One model and one task family; it is not a
measurement of Flywheel's benchmark.

`--prune-duplicates 2` skips the check for a candidate whose partial code
matches two earlier ones. It is off by default. Flywheel's proposers return
whole answers, so today it saves check runs, not generation tokens.

## Re-check a claimed improvement (preview)

`flywheel rederive` accepts a claimed gain only when a verifier the claimant
does not control computed it, on seeds the gate picks, with a mean gain above a
luck margin of twice the standard error, and when a replay of the claimant's
seed matches.

The gate did not meet its pre-registered target, so it ships as a preview. On
20 planted false claims and 13 claims established as true, with 8 gate seeds:

| Method | False claims rejected | True claims accepted |
| :-- | :-- | :-- |
| The gate | 13 of 20, 0.65 [0.43, 0.82] | 13 of 13, 1.00 [0.77, 1.00] |
| Rerun once and compare | 8 of 20, 0.40 [0.22, 0.61] | 12 of 13, 0.92 [0.67, 0.99] |

The target was 95% rejected and 90% accepted. The gate rejected every claim with
an edited metric and every harmful change. It let through 4 of 5 cherry-picked
seeds and 3 of 5 results measured on development data. Each claim it let through
used the baseline's noise rate with a different noisy sample, so its true effect
is zero by our construction and was never measured. One encoder, one task.

Replay certificates for seeded solvers come with it. Two runs on the same seed
must match at every checkpoint. In a separate test, two same-seed runs matched
at 30 of 30 checkpoints (interval 0.886 to 1.000). A match shows the same
computation ran twice. It does not show the answer is right.

## Receipts that say who checked

A routed receipt records whether a machine re-derived a result against an
independent checker, a person re-derived it and signs, or neither applies. The
route is bound into the signed digest, so a machine result relabeled as a
person's sign-off breaks the signature.

## Numbers you can read

Findings can report a score between two anchors: what a trivial method scores
on the same measurement, and the best a repeat of the measurement reaches. Each
anchor carries its source and hash. A finding with a missing anchor reads
"pending".

## An honest way to stop

An agent can return "I could not complete this, and here is why" as a typed
result. The setting `exit_price` decides what that scores. The default is 0, the
same as an honest failure. In a test on twin tasks, a free exit raised false
exits on solvable tasks by 0.20 (interval 0.07 to 0.37) with no measurable drop
in cheating. A configuration that scores an exit below a caught cheat is
refused.

## Red check on pull requests

A report-only check runs each pull request's new tests on the parent commit
and sorts why they fail there. On 158 cases its classes had precision 0.989
(interval 0.940 to 0.998) and recall 1.000 (0.959 to 1.000). It never blocks a
merge. Our measurement found that an agent's own passing tests, including tests
that failed first, do not tell you whether its claim holds on that task.

## Claude Code mod (experimental, unpublished)

The source tree carries an experimental mod under
`integrations/claude-code-mod/`. It routes risky calls through the monitor,
writes a hash-chained receipt per turn and shows held and passed counts above
the prompt. It never approves a call. It has passed 45 tests in a stand-in
runtime and has not run inside Claude Code yet. It needs Claude Code 2.1.287 or
later. It is not published to any marketplace.

## Known limits

- The monitor watches one agent at a time. If one run writes a note to a shared
  folder and another run acts on it, the monitor judges each call alone.
- A request body split across several calls, so that no single call shows a
  URL, can pass. The egress proxy is the complete control for outbound traffic.
- A prompt that mentions an off-list web address in plain text is held. In one
  test, 10 of 10 such ordinary prompts were held. Add the host to `allow_hosts`
  or `fetch_hosts` if this gets in your way.
- A local judge model we tested did not meet our bar for the monitor and is not
  included.

## Evidence

The pre-registrations, results and analysis summaries for the benchmark rerun
and the re-derivation run are in `project-docs/records/1.3.0/`. The full change
list is in `CHANGELOG.md`.
