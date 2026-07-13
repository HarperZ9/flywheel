"""witness.py — re-checkable verdict (HARNESS.md §proof-envelope, the M1 falsifier).

The witness re-runs oracle_cmd against the envelope's candidate and recomputes
the canonical hash. MATCH = a third party reproduces the verdict. DRIFT = the
envelope was tampered (candidate/cmd/outcome diverge). UNVERIFIABLE = the oracle
cannot be re-run. Uses the same canonical_hash() as the oracle so determinism
holds across re-runs.

M2 promotes this to call emet (flagship witness) / sofer (private ledger); the
local re-run stays as the deterministic fallback that needs no external organ.
"""
from __future__ import annotations
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .envelope import ProofEnvelope, load_envelope
from .oracle import canonical_hash, clear_bytecode, run_env


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
    try:
        p = subprocess.run(
            envelope.oracle_cmd, cwd=str(workdir), shell=True, env=run_env(),
            capture_output=True, timeout=timeout)
        reproduced = canonical_hash(envelope.oracle, Path(workdir), p.returncode)
    except subprocess.TimeoutExpired:
        return WitnessVerdict("UNVERIFIABLE", None, "oracle re-run timed out")
    except Exception as e:
        return WitnessVerdict("UNVERIFIABLE", None, f"oracle re-run failed: {e!r}")
    if reproduced == envelope.oracle_output_hash:
        return WitnessVerdict("MATCH", reproduced, "canonical hash reproduced")
    return WitnessVerdict(
        "DRIFT", reproduced,
        f"hash mismatch: envelope={envelope.oracle_output_hash} reproduced={reproduced}")


def witness_envelope_file(envelope_path: str | Path, *, workdir: str | Path,
                          candidate_path: str) -> WitnessVerdict:
    return witness_envelope(load_envelope(envelope_path), workdir=workdir,
                            candidate_path=candidate_path)
