# Pre-registration: adaptive-effort gate in front of search

Written 2026-10-03 before the gated numbers below were computed. The G4 summaries (pass counts per
arm) were already public in project-docs/records/1.3.0/g4-heldout-rerun/ when this was written, and
a consistency count (rows where the first sample passed the visible suite) was taken to confirm the
records can be replayed. No gated pass rate or sample ratio was computed before this file was hashed.

## Decision, owner, change trigger
- Decision: whether search ships an opt-in effort gate and what its docs claim. Owner: Flywheel
  search maturity sprint.
- Bar: the gate keeps at least 90% of search's measured gain (search held-out passes minus single
  held-out passes) while drawing no more than 50% of search's samples. Measured on the G4 secondary
  set (hard_v2, n = 110). The primary set (hard, n = 10) has a measured gain of zero, so retained
  gain is undefined there; it is reported and does not move the decision.
- If the bar fails, the gate still ships off by default and the docs give the numbers.

## Gate rules (fixed here, no parameters fitted)
- first-pass: draw the temperature-0 candidate and run the visible suite on it. If it passes, stop
  and hand it to the decider. Otherwise draw the remaining K - 1 candidates and select as today.
- sequential: stop at the first candidate in proposal order that passes the visible suite.
Search selects the first visible pass in proposal order, so neither gate can change the pick when
generation is deterministic. The measurement checks that claim instead of assuming it.

## Records replay (no model run)
gated_held = single_held when single_visible, else search_held. Samples: 1 when single_visible,
otherwise K = 4. Search samples: 4 per problem. This assumes the single arm's temperature-0
attempt equals search's first candidate; rows where the records contradict that are counted and
reported. The sequential gate cannot be replayed from these records (candidate positions were not
logged); it is reported as a bound only.

## Live confirmation run
Same model (ollama flywheel-local-coder-14b), same split and arms as G4, run once on hard and
hard_v2 with every candidate's visible and held-out verdict logged. Gates are computed by truncating
the logged candidate list, which is exact because a candidate never depends on earlier ones. The
GPU is taken through D:/gpu.lock.d (atomic mkdir, OWNER file); the ollama server is started on
127.0.0.1:11500 and stopped by PID; the lock is released after.

## Metrics
Retained gain = (gated passes - single passes) / (search passes - single passes). Sample ratio =
gated samples / search samples. Paired bootstrap 95% (10,000 resamples over problems, seed 7) on
(gated - search) pass rate and on retained gain (resamples with zero search gain are dropped and
counted). Split-half stability: problems split by a seeded shuffle of task ids (seed 7); the bar is
reported on each half.

## Limits stated in advance
One model, one run. The gate inherits the visible suite's false accepts: 22 of 90 self-scored
accepts on hard_v2 failed the held-out suite in G4, and the gate stops on exactly those passes.
The decider still runs once on the pick, so the gate does not add an accept the held-out suite
rejects. n = 110 cannot resolve a small loss of gain.
