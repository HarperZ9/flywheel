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
from .proposer import Proposer, ProposerOutput, prompt_hash
from .task import Task
from .witness import witness_envelope, WitnessVerdict
from .boot import BootPacket, boot as boot_packet, hydrate_prompt
from .policy import PolicyLayer, PolicyResult, gate as run_gate
from .cache import (ReceiptCache, cache_key, canonical_prompt, knowledge_hash,
                    oracle_context_hash)
from .proof_cache import proof_lookup, proof_insert
from .chain import StageReceipt, append_stage, chain_to_dicts
from .search import best_of_n, DEFAULT_TEMPS
from .eval import ArmConfig
from .grounding import recheck_grounding
from .oracle_inputs import capture as capture_inputs
from .contract_stage import holds, stage_payload, validate_output


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _citation(r) -> dict:
    """Serialise one citation, omitting an empty pin.

    `digest` is dropped while it holds its default, the same rule the envelope
    applies to its own post-hoc fields. An unpinned run therefore hashes exactly
    as it did before pins existed, and a pinned one signs the pin along with
    everything else in `retrieved`.
    """
    d = {"source": r.source, "receipt": r.receipt}
    if getattr(r, "digest", ""):
        d["digest"] = r.digest
    return d


@dataclass
class LoopResult:
    envelope: ProofEnvelope
    oracle: OracleResult | None
    witness: WitnessVerdict | None
    accepted: bool
    elapsed_s: float
    policy: PolicyResult | None = None
    cache_hit: bool = False
    grounding: dict | None = None
    output: dict | None = None


def run_loop(task: Task, proposer: Proposer, oracle: Oracle, *,
             envelopes_dir: str | Path = "envelopes",
             witness_recheck: bool = True,
             boot_packet: BootPacket | None = None,
             boot_root: str | Path | None = None,
             boot_budget: int = 1500,
             policy: list[PolicyLayer] | None = None,
             cache: ReceiptCache | None = None,
             proof_addressed: bool = False,
             search: ArmConfig | None = None,
             grounding_recheck: bool = False,
             grounding_workdirs: dict | None = None,
             capture_oracle_inputs: bool = True,
             output_contract: list[dict] | None = None,
             output_authorities: dict | None = None,
             output_extract=None,
             output_proof=None,
             output_relations=(),
             output_verify_proof: bool = False,
             validation_ledger=None,
             pool: "VerifiedPool | None" = None,
             auto_context: bool = True) -> LoopResult:
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
    retrieved = [_citation(r) for r in task.retrieved]
    # Gap A (memory->context): if the caller passed a VerifiedPool and the task
    # arrived with no retrieved context, populate it from prior verified PASSes.
    # This is the feedback edge that closes the loop -- a verified fact from a
    # prior run becomes available to this proposal. auto_context=False leaves
    # the task untouched (clean ablation). See loop_closure.py handoff
    # memory->context and evolutionary_flywheel.auto_retrieved.
    if auto_context and pool is not None and not task.retrieved:
        from .evolutionary_flywheel import auto_retrieved
        # Match facts whose source key relates to this task (same task_id family
        # or a shared prefix). A pool with no matching facts leaves retrieved empty.
        prereqs = [k for k in pool.facts if k != task.task_id
                   and (k.startswith(task.task_id.split(".")[0])
                        or task.task_id.split(".")[0].startswith(k.split(".")[0]))]
        if prereqs:
            task = auto_retrieved(pool, task, prereqs)
            retrieved = [_citation(r) for r in task.retrieved]
    prompt = task.prompt
    if boot_packet is not None and boot_packet.verdict == "MATCH":
        prompt = hydrate_prompt(boot_packet, prompt)

    ck = None
    cached = None
    oracle_context = oracle_context_hash(task, oracle.oracle_type)
    if cache is not None:
        # A hit supplies a candidate only. The current policy, oracle, witness,
        # grounding, and output contract still decide this run.
        if proof_addressed:
            cached = proof_lookup(cache, task, oracle,
                                  witness_recheck=False,
                                  oracle_context=oracle_context)
        ck = cache_key(task, prompt_hash(canonical_prompt(prompt)),
                       proposer.model_ref, task.seed, task.oracle_cmd,
                       knowledge_hash(task), oracle_context)
        if cached is None:
            cached = cache.lookup(ck)

    # Snapshot the fixtures BEFORE the oracle runs, so this receipt can rebuild
    # its own environment later without a caller handing one over (the fallback
    # in grounding.py). Timing is the whole point: after the run the workdir
    # also holds the candidate and the junit file the canonical hash is read
    # back from, and a receipt carrying its own answer key grades itself.
    oracle_inputs, withheld_inputs = capture_inputs(
        task.workdir, exclude=(task.candidate_path,)
    ) if capture_oracle_inputs else ({}, [])

    search_mode = search is not None and search.n_candidates > 1 and cached is None
    if search_mode:
        sr = best_of_n(task, proposer, oracle,
                       temps=(search.temps or DEFAULT_TEMPS))
        winner = sr.accepted or sr.candidates[0]
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
        if cached is not None:
            out = ProposerOutput(
                text=cached.candidate, model_ref=cached.model_ref,
                seed=cached.seed, prompt_hash=prompt_hash(prompt), cache="hit")
            candidates = 0
        else:
            out = proposer.generate(
                prompt, seed=task.seed, temperature=task.temperature,
                max_new_tokens=task.max_new_tokens, system=task.system)
            candidates = 1
        cand_hash = _short_hash(out.text)
        if cached is not None:
            append_stage(chain, "cache", cached.content_hash(), cand_hash, "HIT",
                         payload={"source_verdict": cached.verdict,
                                  "oracle_context": oracle_context})
        else:
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
                    budget_spent={"candidates": candidates, "oracle_calls": 0},
                    retrieved=retrieved, injected_context=boot_receipt,
                    admission=pr.to_trace(), chain=chain_to_dicts(chain))
                return LoopResult(env, None, None, False, time.time() - t0,
                                  policy=pr, cache_hit=cached is not None)

        orc = oracle.verify(out.text, task)
        append_stage(chain, "verify", cand_hash, orc.output_hash, orc.verdict(),
                     payload={"oracle": oracle.oracle_type, "rc": orc.rc,
                              "oracle_context": oracle_context})
        budget = {"candidates": candidates, "oracle_calls": 1,
                  "proposer_cache": out.cache}
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
        candidate_path=task.candidate_path,
        oracle_inputs=oracle_inputs,
        withheld_inputs=withheld_inputs,
        chain=chain_to_dicts(chain))
    wv = WitnessVerdict("MATCH", orc.output_hash, "witness skipped")
    if witness_recheck:
        wv = witness_envelope(
            envelope, workdir=task.workdir, candidate_path=task.candidate_path)
    append_stage(chain, "accept", orc.output_hash, wv.verdict, wv.verdict,
                 payload={"reason": wv.reason})
    # orc.verdict() never raises; orc.passed raises on a non-dispositive verdict.
    # A domain oracle may legitimately return UNVERIFIABLE (no toolchain, out of
    # scope); that is not acceptance and must not crash the loop.
    accepted = (orc.verdict() == "PASS" and wv.verdict == "MATCH")
    grounding = None
    if grounding_recheck and retrieved:
        # the closure on the critical path: a result is only as good as what it
        # cites — a drifted or unconfirmable grounding gates acceptance (fail
        # closed), while tasks that cite nothing are untouched (localization)
        grounding = recheck_grounding(
            envelope, wv.verdict, envelopes_dir=envelopes_dir,
            workdirs=grounding_workdirs or {})
        append_stage(chain, "grounding",
                     _short_hash(str(sorted(grounding["verdicts"].items()))),
                     grounding["verdict"], grounding["verdict"],
                     payload={"verdicts": grounding["verdicts"],
                              "reasons": grounding["reasons"]})
        accepted = accepted and grounding["verdict"] == "MATCH"
    output = None
    if output_contract:
        # the second closure: a candidate can satisfy its oracle and still
        # disagree with the source that decides its values, because nothing in
        # the oracle asked which source governs. Held answers do not accept,
        # on the same fail-closed rule the grounding recheck uses. A caveat is
        # not a hold, so a contract author sets the strictness by criticality.
        output = validate_output(
            out.text, output_contract, output_authorities or {},
            subject=task.task_id, ledger=validation_ledger,
            extract=output_extract, proof=output_proof,
            relations=output_relations, verify_proof=output_verify_proof)
        append_stage(chain, "output", _short_hash(out.text),
                     output["verdict"], output["release"],
                     payload=stage_payload(output))
        accepted = accepted and not holds(output)
    envelope.chain = chain_to_dicts(chain)
    if accepted:
        epath = Path(envelopes_dir)
        epath.mkdir(parents=True, exist_ok=True)
        envelope.write(epath / f"{task.task_id}-{envelope.content_hash()}.json")
    if cache is not None and ck is not None:
        cache.insert(envelope, ck)
    if cache is not None and proof_addressed:
        proof_insert(cache, task, envelope, oracle_context)
    # Gap A (memory->context): bank the verified fact in the pool so the NEXT
    # task's auto_context can retrieve it. Only PASSes enter (a failed gate
    # must not compound). The receipt hash is the re-checkable handle.
    if pool is not None and accepted:
        pool.add_verified(task.task_id, f"envelope:{envelope.content_hash()}",
                          digest=envelope.content_hash())
    return LoopResult(
        envelope=envelope, oracle=orc, witness=wv,
        accepted=accepted, elapsed_s=time.time() - t0,
        cache_hit=cached is not None, grounding=grounding, output=output)
