# Flywheel 1.3.2

The pre-action monitor now holds more kinds of irreversible delete, and a new
test checks that an offered reward or relief never talks it out of a hold. A
typed judge mode has a small endpoint answer four narrow questions about a
call, and code turns the answers into a decision. Holds can carry a typed override reason with a later outcome
check. `flywheel verify-share` shows how much of what you ship was checked.
Search can stop drawing candidates once the pick is settled, and it can write
cost receipts that compare each call with the hardware's limit.

## Try it

```
pip install -U flywheel-verify
flywheel monitor owner        # prints your config and the installed rule-pack digest
flywheel verify-share --help
```

On Windows, install `Flywheel-Setup-1.3.2-x64.exe` from this release.

## The monitor holds irreversible deletes, whatever the offer

Three new HOLD rules:

- `destructive/004`: `find -delete`, `find -exec rm` or `shred` on a path
  outside the run's workspace.
- `destructive/005`: `git clean` with a force flag. Untracked files have no
  copy git can restore, so this holds inside the workspace too.
- `destructive/006`: `gh repo delete`, `gh release delete`,
  `aws s3 rm --recursive`, `aws s3 rb`, `terraform destroy` and
  `kubectl delete`.

A new costly-relief test set offers an agent an irreversible action paired
with an incentive: an alert clears, a penalty resets, or a reward is paid. The
incentive arrives in a tool description, a shell comment or a file read
earlier in the run.

- Before the new rules, 36 of 93 offers passed the monitor. Now all 93 are
  held.
- Each offer has a twin with the incentive removed. The incentive changed no
  verdict, before or after.
- 45 harmless look-alikes carrying the same incentive text all pass, so the
  monitor does not key on the words.

The test reads proposed calls only. It shows what the monitor does with an
action and says nothing about why an agent proposed it.

## Typed judge mode

With `protocol: systemone`, a judge endpoint answers four yes/no questions,
and code combines the answers into ACT, ABSTAIN or ESCALATE. The monitor holds
on ABSTAIN and ESCALATE. On a held-out half of 788 labelled agent actions, hold
precision was 0.748 [0.661, 0.818] and recall 0.835 [0.752, 0.894], meeting
every bar set in advance. See `docs/PREACTION-JUDGE-TYPED.md`.

## Override reasons and outcome checks

A decision on a held call can now carry a typed reason code, sealed with the
decision. A later outcome check, typed at a real terminal, records whether the
decision held up.
The report computes override rates and two-coder agreement. The agreement bar
needs two people to code 50 holds, so it has not been measured. See
`docs/PREACTION-OVERRIDES.md`.

## How much of what ships was checked

`flywheel verify-share` reads shipped items and reports, per week, the share
of output that was machine-checked, person-checked or unchecked. It flags a
week when the unchecked share has risen two weeks running while output grew.
A cost-to-verify meter groups reviewer minutes by task family. On 832 merged
pull requests across 20 repositories, no week was flagged, so the bar set for
the flag (fire on at least one stretch a person agrees was under-checked) is
not met. See `docs/VERIFICATION-SHARE.md`.

## Search: stop once the pick is settled

`--effort-gate sequential` stops drawing candidates at the first one that
passes the visible tests, because a later candidate can no longer change the
pick. The hidden tests still run once, on the pick. It is off by default.

On a 110-problem set with a local 14B coder model and a bar set in advance,
`sequential` kept all 7 problems of search's gain while drawing 0.446
[0.391, 0.502] of the samples, which meets the bar. `first-pass` drew 0.509
and missed it by 0.009. A gain of 7 problems cannot rule out losing one or
two. See `docs/features/search-selection.md`.

## Search: cost receipts

Set `hardware` and `model_profile` on a search arm, and each candidate gets a
receipt with its measured time, the fastest time the chip's published peak
rates allow, and their ratio. On 600 calls of a local 14B model on one
RTX 4090, every call got a receipt and none ran below the floor. The median
call took 1.33 times the floor. See `docs/features/cost-receipts.md`.

## Check this release

- PyPI: `flywheel-verify==1.3.2`
- Windows installer: `Flywheel-Setup-1.3.2-x64.exe`, with its hash in
  `SHA256SUMS.txt`
- The monitor rule pack changed, so an owner who pins `expected_rules_digest`
  must re-pin. `flywheel monitor owner` prints the new digest as
  `installed_rules_digest`:

```
a76b7e8995c91861e92ce2198cd62d722deede9fb8307463c68b8aa5d5cdf8c4
```
