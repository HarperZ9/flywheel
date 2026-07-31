"""gate.py -- the Phase 0 disproof gate.

One command that takes the existing chain end to end: an exact symbolic oracle
disposes a group of candidate matmul schemes, the group is scored with the named
estimator, the accepted candidate is sealed into a proof envelope, and the
envelope is re-witnessed by re-running the same oracle over the stored candidate.

Everything here already existed in the repository and was never wired together.
If this command cannot reach MATCH, the premise that these parts compose is
false, and we learn it in week one for the price of a week.

There is no model in this gate, deliberately. The proposer is a deterministic
local function, so what is under test is the oracle plus group plus receipt plus
re-witness chain, not generation. A gate whose result depended on a model would
be measuring the wrong thing.

The oracle never executes candidate code: it checks a data structure against an
exact tensor identity over the rationals. That is the property that makes the
whole chain safe to hand to a stranger.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .envelope import ProofEnvelope
from .matmul_oracle import (
    MatMulSchemeOracle, strassen_scheme, perturb_scheme, dumps,
)
from .rl_from_oracle import RLFromOracle
from .task import Task
from .verdict import Verdict

GROUP_SIZE = 4
TEMPERATURE = 1.0
ESTIMATOR = "drgrpo"


@dataclass
class GateReport:
    verdict: str
    group_signal_hash: str
    envelope_hash: str
    claim_hash: str
    rewitness: str
    steps: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"verdict": self.verdict,
                "group_signal_hash": self.group_signal_hash,
                "envelope_hash": self.envelope_hash,
                "claim_hash": self.claim_hash,
                "rewitness": self.rewitness,
                "steps": self.steps}


class _SchemeProposer:
    """Deterministic stand-in for a policy: seed 0 yields the correct Strassen
    scheme, every other seed yields a perturbed one. The pool is deliberately
    mixed so the group carries a gradient and the gate exercises the learnable
    path rather than the degenerate all-fail one."""

    model_ref = "gate:deterministic-scheme-proposer"

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        scheme = (strassen_scheme() if seed % GROUP_SIZE == 0
                  else perturb_scheme(strassen_scheme(), triple=seed % 7,
                                      field="w", pos=seed % 4))

        class _Out:
            text = dumps(scheme)
        return _Out()


def _task() -> Task:
    return Task(task_id="gate-matmul-2x2x2",
                prompt="Emit a rank-7 bilinear scheme for 2x2x2 matmul.",
                oracle="matmul_bilinear", oracle_cmd="matmul_identity",
                workdir=".", candidate_path="scheme.json",
                max_new_tokens=4096)


def rewitness_envelope(path) -> str:
    """Re-run the oracle over the stored candidate and compare to the sealed
    record. MATCH, DRIFT, or UNVERIFIABLE. Never assumes MATCH: a missing or
    unreadable envelope is a gap in the record, not a pass."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return "UNVERIFIABLE"
    if not isinstance(d, dict):
        return "UNVERIFIABLE"
    candidate = d.get("candidate")
    if candidate is None:
        return "UNVERIFIABLE"
    res = MatMulSchemeOracle().verify(candidate, None)
    if res.verdict() != d.get("verdict"):
        return "DRIFT"
    if res.output_hash != d.get("oracle_output_hash"):
        return "DRIFT"
    return "MATCH"


def run_gate(out_dir) -> GateReport:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []

    oracle = MatMulSchemeOracle()
    task = _task()

    rl = RLFromOracle(_SchemeProposer(), group_size=GROUP_SIZE,
                      temperature=TEMPERATURE, estimator=ESTIMATOR)
    group = rl.collect(task, oracle)
    steps.append({"step": "collect", "group_size": GROUP_SIZE,
                  "temperature": group.temperature, "estimator": group.estimator,
                  "n_pass": group.n_pass, "learnable": group.learnable,
                  "n_undecided": group.n_undecided, "n_excluded": group.n_excluded,
                  "signal_hash": group.signal_hash})

    winner = next((r for r in group.rollouts if r.reward >= 1.0), None)
    if winner is None:
        report = GateReport(verdict=Verdict.UNVERIFIABLE.value,
                            group_signal_hash=group.signal_hash,
                            envelope_hash="", claim_hash="",
                            rewitness="UNVERIFIABLE", steps=steps)
        (out_dir / "gate_report.json").write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return report

    res = oracle.verify(winner.text, task)
    steps.append({"step": "verify", "verdict": res.verdict(),
                  "output_hash": res.output_hash,
                  "attribution": res.attribution.value})

    env = ProofEnvelope(
        task_id=task.task_id, candidate=winner.text, oracle=oracle.oracle_type,
        oracle_cmd="matmul_identity", oracle_output_hash=res.output_hash,
        verdict=res.verdict(), model_ref=_SchemeProposer.model_ref,
        seed=winner.seed, prompt_hash=group.prompt_hash,
        budget_spent={"oracle_calls": GROUP_SIZE + 1},
        oracle_stdout_excerpt=res.stdout_excerpt)
    env_path = out_dir / "gate_envelope.json"
    env_path.write_text(env.to_json(), encoding="utf-8")
    steps.append({"step": "seal", "envelope_hash": env.content_hash(),
                  "claim_hash": env.claim_hash(), "path": str(env_path)})

    verdict_of_rewitness = rewitness_envelope(env_path)
    steps.append({"step": "rewitness", "result": verdict_of_rewitness})

    report = GateReport(verdict=res.verdict(), group_signal_hash=group.signal_hash,
                        envelope_hash=env.content_hash(), claim_hash=env.claim_hash(),
                        rewitness=verdict_of_rewitness, steps=steps)
    (out_dir / "gate_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return report
