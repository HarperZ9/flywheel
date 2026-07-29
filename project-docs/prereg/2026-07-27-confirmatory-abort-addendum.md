# Preregistration addendum: confirmatory run aborted, and the rerun that cites it

**Addendum to:** `prereg.size-invariant-verification.v1`, frozen sha256
`31055c924d48fe67ebdf29ab8f067840f83ccc6ff1d1f469bc0abb2be0dffa08`.

**Status:** FROZEN when this file's sha256 is appended to the ledger as a
`confirmatory-abort` event. This document does not edit the frozen
preregistration. It discharges the parent's own requirement (parent section 7)
that an aborted run be logged with its reason and that the rerun be a new hash
citing the aborted one.

**Register:** the `research` profile. Calibrated uncertainty is kept.

---

## 1. What was attempted

The first confirmatory pass launched 2026-07-27 and walked the fixed order of
eighteen (family, rung) pairs, calling the fill driver once per pair. Its
mechanical journal is `artifacts/pool/confirmatory-journal.jsonl`. That journal
records only started, finished, exit code and wall seconds per pair: the walker
was built unable to read a verdict or aggregate an outcome, because parent
section 7 forbids interim analysis.

## 2. What happened, and why it is a MECHANICAL abort

Twelve of eighteen pairs failed. The exit codes name the cause exactly:

| code | meaning | pairs |
|---|---|---|
| `0x40010004` | `DBG_TERMINATE_PROCESS` | 1, killed at 2399s mid-generation |
| `0xC0000142` | `STATUS_DLL_INIT_FAILED` | 11, each in 0.0 seconds |

The signature is unambiguous. The interactive session that launched the walk
ended; its teardown killed the child then generating, and every subsequent
subprocess could no longer initialize, failing instantly. The walker continued
per its own design (a failing pair does not stop the walk, because the remaining
pairs are independent generation work) and wrote `run_end` with
`pairs_failed: 12`.

This is a mechanical abort in the parent's sense. Nothing about a candidate, a
checker, a verdict, or an outcome caused it. No outcome was read at any point.

**Root cause, stated plainly.** The run was launched with `nohup ... &` from a
session-bound shell on Windows, on the assumption that this detaches the process
from the session. It does not: `nohup` guards against SIGHUP, while Windows
console and job-object teardown kills the process tree regardless. The
durability was asserted rather than tested. A second, independent session in the
same workspace observed the same class of failure over the same boundary on
unrelated services, which corroborates the diagnosis as a property of the
environment rather than of this run.

## 3. What survived, and why it is NOT reused

Six pairs completed with exit 0, all in the `zarankiewicz` family: rungs
`qwen2.5:0.5b`, `qwen2.5:1.5b`, `qwen2.5:3b`, `qwen2.5:7b`, `olmo2:7b`, and
`telos-coder-14b`. Their pools are on disk and content-addressed.

**They are not carried into the rerun.** Mixing pools generated across two runs
under one preregistration is precisely the provenance ambiguity the stopping
rule exists to prevent: a reader could not tell which candidates came from the
aborted pass and which from the confirmatory one, and the fingerprint alone
would not disambiguate them because it is identical by design. The surviving
pools are retained as an ARTIFACT OF THE ABORTED RUN, under
`artifacts/pool-aborted-2026-07-27/`, and are cited by nothing.

## 4. The rerun

The rerun uses the same frozen instance set, the same K, the same seed list, the
same nine rungs and two families, and the same fingerprint fields as the parent.
Nothing about the protocol changes. Two things change about the MECHANISM, and
both are recorded here because they are the reason to believe the rerun can
finish:

1. **Durable execution.** The walk runs detached from any interactive session,
   under an execution mechanism whose independence is verified structurally
   before launch rather than assumed, by confirming the running process does not
   descend from an interactive shell.
2. **Resumability.** The walker skips a pair whose output directory already
   carries a completed marker, so a future mechanical interruption costs only
   the pair in flight. Resumption is mechanical only and reads no outcome.

This addendum does not predict a result and does not relax an endpoint. The
primary endpoint, the arms, the controls, and the claim rule are the parent's
unchanged.

## 5. Does not prove

- **NOT_PROVES_THE_RERUN_COMPLETES.** A verified-independent launch mechanism
  removes the failure that ended the first pass. It does not bound power loss,
  a driver crash, thermal shutdown, or a defect not yet met.
- **NOT_PROVES_THE_ABORTED_POOLS_ARE_WRONG.** The six surviving pools are
  retired for provenance hygiene, not because anything about them is known to
  be defective. Retiring them is the conservative choice, not a verdict.
- **NOT_PROVES_NO_OUTCOME_WAS_SEEN.** The walker cannot read outcomes and no
  analysis was run, so no outcome informed this addendum. That is a property of
  the tooling and this record, checkable by reading both, and not a claim about
  anybody's memory.
