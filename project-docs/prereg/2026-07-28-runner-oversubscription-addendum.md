# Preregistration addendum: a third interruption, an orphaned model runner, and two walkers at once

**Addendum to:** `prereg.size-invariant-verification.v1`, frozen sha256
`31055c924d48fe67ebdf29ab8f067840f83ccc6ff1d1f469bc0abb2be0dffa08`.

**Continues:** the confirmatory-abort addendum, sha256
`09a19497f90ddedc93d297404334c31b62127fe91d5dc1d72dda44d464d87a76`, which
covers the first two interruptions and established that a mechanical
interruption costs only the pair in flight.

**Status:** FROZEN when this file's sha256 is appended to the ledger as a
`runner-oversubscription` event. It does not edit the frozen preregistration, and
it changes no arm, endpoint, instance, seed, or claim rule. It records a
mechanical event, one quarantine of generated data, and one repair.

**Register:** the `flavored` profile. Calibrated uncertainty is kept.

---

## 1. Timeline, in UTC, from process and server records

| when | what |
|---|---|
| 04:15:55 | A model runner starts for `telos-coder-32b`. The walk begins the `zarankiewicz` pair on that rung. |
| 06:16:05 | The last of 52 candidate files for that pair is written. Rate over the interval: roughly one candidate every 140 seconds. |
| about 06:17 | The interactive session ends. The walker dies. **Its model runner does not.** |
| 06:20:37 | Recovery launch A. It skips the seven finished pairs and restarts the 32B pair. |
| 06:26:31 | The server starts a SECOND runner for the same model blob, because the orphaned first runner is still resident. |
| 06:59:00 | A second hand-typed recovery launch, B. Two walkers now target one pair. |
| 07:12 | Both walkers are stopped. |
| 07:25 | The model is unloaded and the orphaned runner is stopped. |
| 07:26:10 | One walker is started through the scheduled-task path, so its parent is the task service and not a session. |
| 07:31:52 | Seven candidates written since the restart. Generation is working. |

## 2. Two separate faults, named separately

**Fault one, throughput.** Two runners for one 28 GB model on a 24 GB device
oversubscribe it. Every generation request then exceeded the client's 600 second
ceiling: the server log shows repeated `POST /api/generate` returning 500 after
exactly `10m0s`, with the corresponding tasks cancelled. Across the whole
interval from 06:20:37 to 07:12, spanning both walkers, ZERO candidates were
written. The driver behaved correctly throughout, recording each timed-out slot
as an error with a null digest rather than treating it as a candidate.

**Fault two, concurrency.** Two walkers ran at once and both aimed at the same
(family, rung) pair, writing into the same pool directory. That is not the single
pass the parent's stopping rule allows, independent of throughput. The cause was
plain: the supervisor refused to add a walk while one was alive, but a hand-typed
launch bypassed that check because the walker itself had none.

## 3. What entered the pool: nothing

Checked rather than assumed. Across the whole pool tree, exactly two files were
modified during the interval in which two walkers were live: the mechanical
progress journal and the supervisor's own log. No candidate, no pool index, and
no run manifest was written. The pair also never reached the point where an index
is written, so no completed pair carries any trace of the concurrent window.

## 4. The quarantine, and that it was conservative

The 52 candidates walker one had produced for the `zarankiewicz` pair on
`telos-coder-32b` were moved out of the pool before the restart, so the pair
regenerates into an empty directory. Stated plainly: that call was made BEFORE
the diagnosis was complete, on the reasoning that a partial directory whose index
is written by a later run would hold files the index does not reference.

Two honest qualifications:

- The cost is time, not correctness. Every slot is generated under a pinned seed,
  so the regenerated candidates are expected to be byte-identical to the
  quarantined ones. That expectation is checkable later against the quarantined
  copies, and it has not been checked yet.
- The candidate store writes a file only when its content-addressed path is
  absent. So a resumed pair that re-derives identical text writes nothing, which
  means "no new files" was WEAK evidence of a stall on its own. The strong
  evidence is the server's own record of requests failing at the client ceiling.

## 5. The repair

1. **A one-walk guard in the walker.** It refuses to start when another walker is
   live, reading live process command lines rather than a pidfile, because a
   pidfile left by a killed process is the stale state this has to survive. The
   guard excludes both itself and any non-interpreter process whose command line
   merely quotes the script's name, so a wrapped launch is not mistaken for a
   rival. Verified by removing the exclusion and watching the covering test fail.
2. **Runner hygiene before relaunch.** The model was unloaded and the orphaned
   runner stopped, so exactly one runner serves the rung.
3. **A launch whose parent is not a session,** through the scheduled task, as the
   previous addendum required.

## 6. A correction to an earlier reading

The device reports a 20 percent processor split for this rung, and the first
reading here attributed that split to the duplicate runner. That was wrong. The
split reproduced with a single runner on an otherwise idle device, so it follows
from a 28 GB footprint at the witnessed 32768 context length on a 24 GB device
and is STRUCTURAL for the 32B rungs.

The consequence is recorded rather than fixed: the 32B rungs are slow by
construction, and the witnessed context length is part of the serving surface
this preregistration pinned. Reducing it would make the rung fast and would also
change the surface mid-pass, so it is not reduced.

## 7. Does not prove

- **NOT_PROVES_THE_WALK_COMPLETES.** One guard and one clean runner remove the
  two faults met here. Neither bounds a power loss, a driver fault, or a defect
  not yet met.
- **NOT_PROVES_THE_QUARANTINED_CANDIDATES_ARE_WRONG.** They are set aside for
  provenance hygiene. Nothing about them is known to be defective, and the
  byte-identity check against their replacements has not been run.
- **NOT_PROVES_NO_OUTCOME_WAS_SEEN.** The walker and the supervisor are both
  built unable to read a verdict, and no analysis has run. That is checkable by
  reading them, and it is not a claim about anybody's memory.
- **NOT_PROVES_THE_RATE_ESTIMATE.** The post-repair rate is measured over the
  first few minutes of the easiest difficulty band. Later instances produce
  longer outputs, so the observed rate is a lower bound on total cost, not a
  forecast.
- **NOT_PROVES_THE_600_SECOND_CEILING_IS_RIGHT.** The ceiling was not changed
  during the pass, because changing the generation mechanism mid-pass is exactly
  what the stopping rule guards against. Whether it is the correct ceiling for a
  32B rung is an open question for the next pass, not a finding of this one.
