"""witness.py — re-checkable verdict (HARNESS.md §proof-envelope, the M1 falsifier).

The witness re-runs oracle_cmd against the envelope's candidate and recomputes
the canonical hash. MATCH = a third party reproduces the verdict. DRIFT = the
envelope was tampered (candidate/cmd/outcome diverge). UNVERIFIABLE = the oracle
cannot be re-run. Uses the same hashing as the oracle so determinism holds
across re-runs.

A matching hash is not enough on its own. An envelope can seal a failing run's
own hash under a PASS verdict, and before 2026-09-23 that re-witnessed MATCH:
a bare os._exit(0) candidate claimed PASS with the hash of its empty outcomes.
For a pytest envelope the witness now also grades the re-run
(junit_report.grade) and returns DRIFT when the sealed verdict differs. Other
oracle types have an empty canonical form, so their verdict is not re-derived
here and a MATCH for them still means only "it exited the same way".

The re-run reads outcomes from its own per-run JUnit report, never from a
report an earlier run left in the workdir (junit_report.py). A witness run in
the oracle's own workdir would otherwise reproduce the stale outcomes the
oracle read and return MATCH on them.

M2 promotes this to call emet (flagship witness) / sofer (private ledger); the
local re-run stays as the deterministic fallback that needs no external organ.
"""
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .envelope import ProofEnvelope, load_envelope
from .junit_report import bind_report, discard_report
from .oracle import clear_bytecode, rerun_outcome, run_env


@dataclass
class WitnessVerdict:
    verdict: str  # MATCH | DRIFT | UNVERIFIABLE
    reproduced_hash: str | None
    reason: str


def witness_envelope(envelope: ProofEnvelope, *, workdir: str | Path,
                     candidate_path: str, timeout: int = 60) -> WitnessVerdict:
    cpath = Path(workdir) / candidate_path
    cpath.parent.mkdir(parents=True, exist_ok=True)
    cpath.write_text(envelope.candidate, encoding="utf-8")
    clear_bytecode(Path(workdir))
    run_cmd, report = bind_report(envelope.oracle_cmd, workdir)
    try:
        p = subprocess.run(
            run_cmd, cwd=str(workdir), shell=True, env=run_env(),
            capture_output=True, timeout=timeout)
        reproduced, graded = rerun_outcome(envelope.oracle, p.returncode, report)
    except subprocess.TimeoutExpired:
        return WitnessVerdict("UNVERIFIABLE", None, "oracle re-run timed out")
    except Exception as e:
        return WitnessVerdict("UNVERIFIABLE", None, f"oracle re-run failed: {e!r}")
    finally:
        discard_report(report)
    if reproduced != envelope.oracle_output_hash:
        return WitnessVerdict(
            "DRIFT", reproduced,
            f"hash mismatch: envelope={envelope.oracle_output_hash} reproduced={reproduced}")
    if graded is not None and graded.value != envelope.verdict:
        return WitnessVerdict(
            "DRIFT", reproduced,
            f"verdict mismatch: envelope claims {envelope.verdict}, "
            f"the re-run's outcomes support {graded.value}")
    return WitnessVerdict("MATCH", reproduced, "canonical hash reproduced")


def witness_envelope_file(envelope_path: str | Path, *, workdir: str | Path,
                          candidate_path: str) -> WitnessVerdict:
    return witness_envelope(load_envelope(envelope_path), workdir=workdir,
                            candidate_path=candidate_path)
