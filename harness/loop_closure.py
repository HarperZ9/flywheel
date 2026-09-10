"""Measure bounded deterministic handoffs; report structural paths separately.

This instrument exercises a fixture oracle and a deterministic memory reader.
It does not measure learned-model utility, alignment, automatic configuration
application or training. A function's presence cannot establish loop closure.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
import json


@dataclass
class Handoff:
    frm: str
    to: str
    carries: str
    closed: bool
    verified: bool  # An execution was observed; inspect closed for its outcome.
    evidence: str


class _MemoryReader:
    model_ref = "closure-memory-reader"

    def __init__(self):
        self.inputs = []

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        from .proposer import ProposerOutput, prompt_hash
        self.inputs.append(prompt)
        rows = [json.loads(line) for line in prompt.splitlines()
                if line.startswith('{"memory_source":')]
        text = rows[0]["content"] if rows else "def add(a, b):\n    return 0\n"
        return ProposerOutput(text, self.model_ref, seed, prompt_hash(prompt), "off")


def measure_loop(tmp_dir) -> dict:
    from pathlib import Path
    from .task import load_task
    from .proposer import StubProposer, prompt_hash
    from .oracle import PytestOracle
    from .loop import run_loop
    from .cache import ReceiptCache
    from .evolutionary_flywheel import VerifiedPool

    fixture = Path(__file__).parent.parent / "tasks" / "example_pass"
    correct = "def add(a, b):\n    return a + b\n"
    tmp = Path(tmp_dir)
    hs = []
    control = {"executed": False, "enabled_accepted": False,
               "disabled_accepted": False, "prompt_changed": False,
               "source_in_actual_input": False}
    try:
        task = replace(load_task(fixture, workdir=tmp / "seed"), task_id="closure.seed")
    except OSError:
        task = None
    if task is not None:
        pool, cache = VerifiedPool(), ReceiptCache(tmp / "cache")
        source = run_loop(task, StubProposer(correct), PytestOracle(),
                          pool=pool, cache=cache, envelopes_dir=tmp / "env")
        hs.append(Handoff("propose", "verify", "candidate", source.accepted, True,
                          "fixture oracle and witness executed"))
        hs.append(Handoff("verify", "memory", "accepted claim",
                          pool.claim_digests.get(task.task_id) == source.envelope.claim_sha256(),
                          True, "accepted claim digest banked in the pool"))
        repeat = run_loop(task, StubProposer("raise AssertionError('cache miss')"),
                          PytestOracle(), cache=cache, envelopes_dir=tmp / "env")
        hs.append(Handoff("memory", "serve", "cached candidate",
                          repeat.cache_hit and repeat.accepted, True,
                          "repeat run reused candidate and rechecked current oracle"))
        target = replace(load_task(fixture, workdir=tmp / "target"), task_id="closure.target")
        on, off = _MemoryReader(), _MemoryReader()
        args = dict(pool=pool, memory_sources=[task.task_id], envelopes_dir=tmp / "env")
        enabled = run_loop(target, on, PytestOracle(), **args)
        disabled = run_loop(target, off, PytestOracle(), auto_context=False, **args)
        actual = on.inputs[0]
        records = [json.loads(line) for line in actual.splitlines()
                   if line.startswith('{"memory_source":')]
        control = {"executed": True, "enabled_accepted": enabled.accepted,
                   "disabled_accepted": disabled.accepted,
                   "prompt_changed": actual != off.inputs[0],
                   "source_in_actual_input": any(r == {"memory_source": task.task_id,
                                                        "content": correct} for r in records),
                   "enabled_prompt_hash": prompt_hash(actual),
                   "disabled_prompt_hash": prompt_hash(off.inputs[0])}
    else:
        for frm, to, carries in [("propose", "verify", "candidate"),
                                 ("verify", "memory", "claim"), ("memory", "serve", "candidate")]:
            hs.append(Handoff(frm, to, carries, False, False, "fixture unavailable; not executed"))
    memory_closed = (control["executed"] and control["enabled_accepted"]
                     and not control["disabled_accepted"] and control["prompt_changed"]
                     and control["source_in_actual_input"])
    hs.append(Handoff("memory", "context", "authorized candidate content", memory_closed,
                      control["executed"], "deterministic dependent task with retrieval ablation"))
    # Available plumbing and surfaced candidates remain explicitly unexecuted.
    for frm, to, carries, evidence in [
        ("perceive", "propose", "boot context", "structural boot path; not measured here"),
        ("verify", "evolve", "configuration proposals", "spin surfaces meta_cycle proposals; not measured here"),
        ("evolve", "propose", "configuration change", "proposal-only; spin does not apply candidates"),
        ("verify", "corpus", "experience export", "structural corpus path; not measured here"),
        ("corpus", "model", "trained weights", "export is not training; operator-gated training not executed")]:
        hs.append(Handoff(frm, to, carries, False, False, evidence))
    n_closed = sum(h.closed and h.verified for h in hs)
    return {"handoffs": [h.__dict__ for h in hs], "memory_control": control,
            "n_handoffs": len(hs), "n_closed": n_closed,
            "closure_fraction": round(n_closed / len(hs), 3),
            "fully_closed": n_closed == len(hs),
            "open_links": [f"{h.frm}->{h.to}" for h in hs if not h.closed],
            "executed_links": [f"{h.frm}->{h.to}" for h in hs if h.verified],
            "does_not_prove": "Learned-model utility, alignment, automatic configuration application or training."}


def loop_report(m: dict) -> str:
    return (f"loop closure {m['n_closed']}/{m['n_handoffs']} ({m['closure_fraction']:.0%}); "
            f"{len(m['executed_links'])} executed; open or unmeasured: {', '.join(m['open_links']) or 'none'}")
