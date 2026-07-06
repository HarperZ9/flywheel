"""loop.py — the M1 minimal witnessed loop (HARNESS-ROADMAP.md M1).

task -> retrieve -> propose -> oracle-verify -> envelope -> witness.

This is the smallest end-to-end receipt. M2 extends the envelope into a
per-stage carried chain; M3 adds best-of-N; M4 adds escalation. The chain
pattern is established here so those are extensions, not rewrites.

No receipt -> no accept: if the witness does not return MATCH, the loop returns
UNVERIFIABLE and emits no accepting envelope.
"""
from __future__ import annotations
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from .envelope import ProofEnvelope
from .oracle import Oracle, OracleResult
from .proposer import Proposer, prompt_hash
from .task import Task
from .witness import witness_envelope, WitnessVerdict
from .boot import BootPacket, boot as boot_packet, hydrate_prompt
from .policy import PolicyLayer, PolicyResult, gate as run_gate
from .cache import ReceiptCache, cache_key
from .proof_cache import proof_lookup, proof_insert
from .chain import StageReceipt, append_stage, chain_to_dicts
from .search import best_of_n, DEFAULT_TEMPS
from .eval import ArmConfig


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class LoopResult:
    envelope: ProofEnvelope
    oracle: OracleResult | None
    witness: WitnessVerdict | None
    accepted: bool
    elapsed_s: float
    policy: PolicyResult | None = None
    cache_hit: bool = False


def run_loop(task: Task, proposer: Proposer, oracle: Oracle, *,
             envelopes_dir: str | Path = "envelopes",
             witness_recheck: bool = True,
             boot_packet: BootPacket | None = None,
             boot_root: str | Path | None = None,
             boot_budget: int = 1500,
             policy: list[PolicyLayer] | None = None,
             cache: ReceiptCache | None = None,
             proof_addressed: bool = False,
             search: ArmConfig | None = None) -> LoopResult:
    t0 = time.time()
    chain: list[StageReceipt] = []
    if boot_packet is None and boot_root is not None:
        boot_packet = boot(boot_root, budget=boot_budget, focus=task.task_id)
    boot_receipt = None
    if boot_packet is not None:
        boot_receipt = boot_packet.root_receipt()
        append_stage(chain, "boot", task.task_id,
                     boot_packet.root_hash, boot_packet.verdict,
                     payload={"git_head": boot_packet.git_head})
    retrieved = [{"source": r.source, "receipt": r.receipt}
                 for r in task.retrieved]
    prompt = task.prompt
    if boot_packet is not None and boot_packet.verdict == "MATCH":
        prompt = hydrate_prompt(boot_packet, prompt)

    ck = None
    if cache is not None:
        # Proof-addressed hit (opt-in, SERVING mode): prompt- AND model-invariant
        # (fixes the F2 0% agent cache-hit from volatile prompt headers),
        # re-witnessed, served only on MATCH. OFF by default because the fact-key
        # omits model_ref/prompt: a second model would hit the first's verified
        # result, which is exactly WRONG for A/B eval (M7) — so eval leaves it
        # off and serving turns it on. A proof-hit skips the proposer but pays
        # one oracle re-run (the C2 re-verification tax).
        if proof_addressed:
            phit = proof_lookup(cache, task, oracle)
            if phit is not None:
                return LoopResult(phit, None, None,
                                  phit.verdict == "PASS", time.time() - t0,
                                  cache_hit=True)
        ck = cache_key(task, prompt_hash(prompt), proposer.model_ref,
                       task.seed, task.oracle_cmd)
        cached = cache.lookup(ck)
        if cached is not None:
            return LoopResult(cached, None, None,
                              cached.verdict == "PASS", time.time() - t0,
                              cache_hit=True)

    search_mode = search is not None and search.n_candidates > 1
    if search_mode:
        sr = best_of_n(task, proposer, oracle,
                       temps=(search.temps or DEFAULT_TEMPS))
        winner = sr.accepted or sr.candidates[0]
        from .proposer import ProposerOutput
        out = ProposerOutput(text=winner.text, model_ref=winner.model_ref,
                             seed=winner.seed, prompt_hash=winner.prompt_hash,
                             cache="search")
        orc = winner.oracle_result if winner.oracle_result else OracleResult(
            passed=False, cmd=task.oracle_cmd, output_hash="",
            stdout_excerpt="", rc=1)
        cand_payload = [{"temp": c.temperature,
                         "candidate_hash": _short_hash(c.text),
                         "verdict": c.oracle_result.verdict() if c.oracle_result else "NONE",
                         "oracle_output_hash": c.oracle_result.output_hash if c.oracle_result else ""}
                        for c in sr.candidates]
        append_stage(chain, "search", prompt_hash(prompt),
                     _short_hash(winner.text),
                     sr.verdict,
                     payload={"n": len(sr.candidates), "correlation": round(sr.correlation, 3),
                              "candidates": cand_payload})
        budget = {"candidates": len(sr.candidates),
                  "oracle_calls": len(sr.candidates), "proposer_cache": "search"}
    else:
        out = proposer.generate(
            prompt, seed=task.seed, temperature=task.temperature,
            max_new_tokens=task.max_new_tokens, system=task.system)
        cand_hash = _short_hash(out.text)
        append_stage(chain, "propose", out.prompt_hash, cand_hash, "OK",
                     payload={"model_ref": out.model_ref, "seed": out.seed,
                              "cache": out.cache})

        if policy is not None:
            pr = run_gate(policy, "oracle.run", {
                "cmd": task.oracle_cmd, "workdir": task.workdir,
                "candidate_hash": cand_hash, "task_id": task.task_id})
            append_stage(chain, "policy", pr.args_hash, pr.decision.value,
                         pr.decision.value,
                         payload={"policy_id": pr.policy_id,
                                  "reason_code": pr.reason_code})
            if not pr.allowed:
                env = ProofEnvelope(
                    task_id=task.task_id, candidate=out.text, oracle=oracle.oracle_type,
                    oracle_cmd=task.oracle_cmd, oracle_output_hash="",
                    verdict="BLOCKED", model_ref=out.model_ref, seed=out.seed,
                    prompt_hash=out.prompt_hash,
                    budget_spent={"candidates": 1, "oracle_calls": 0},
                    retrieved=retrieved, injected_context=boot_receipt,
                    admission=pr.to_trace(), chain=chain_to_dicts(chain))
                return LoopResult(env, None, None, False, time.time() - t0, policy=pr)

        orc = oracle.verify(out.text, task)
        append_stage(chain, "verify", cand_hash, orc.output_hash, orc.verdict(),
                     payload={"oracle": oracle.oracle_type, "rc": orc.rc})
        budget = {"candidates": 1, "oracle_calls": 1, "proposer_cache": out.cache}
    envelope = ProofEnvelope(
        task_id=task.task_id,
        candidate=out.text,
        oracle=oracle.oracle_type,
        oracle_cmd=orc.cmd,
        oracle_output_hash=orc.output_hash,
        verdict=orc.verdict(),
        model_ref=out.model_ref,
        seed=out.seed,
        prompt_hash=out.prompt_hash,
        budget_spent=budget,
        retrieved=retrieved,
        oracle_stdout_excerpt=orc.stdout_excerpt,
        injected_context=boot_receipt,
        chain=chain_to_dicts(chain))
    wv = WitnessVerdict("MATCH", orc.output_hash, "witness skipped")
    if witness_recheck:
        wv = witness_envelope(
            envelope, workdir=task.workdir, candidate_path=task.candidate_path)
    append_stage(chain, "accept", orc.output_hash, wv.verdict, wv.verdict,
                 payload={"reason": wv.reason})
    envelope.chain = chain_to_dicts(chain)
    accepted = (orc.passed and wv.verdict == "MATCH")
    if accepted:
        epath = Path(envelopes_dir)
        epath.mkdir(parents=True, exist_ok=True)
        envelope.write(epath / f"{task.task_id}-{envelope.content_hash()}.json")
    if cache is not None and ck is not None:
        cache.insert(envelope, ck)
    if cache is not None and proof_addressed:
        proof_insert(cache, task, envelope)   # dual-index: prompt/model-invariant fact
    return LoopResult(
        envelope=envelope, oracle=orc, witness=wv,
        accepted=accepted, elapsed_s=time.time() - t0)
