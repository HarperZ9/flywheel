# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""J14 Checked-Claim Economy Benchmark Arena (60 Multi-Step Math/Code/Physics Tasks)."""
from __future__ import annotations

import math
from typing import Any

from harness.epigenetics_economy.checked_economy import (
    CheckedClaimMarketplace,
    LemmaReceipt,
    LemmaSpec,
    MultiStepTask,
    SpecialistAgent,
    oracle_eval_final,
    oracle_eval_lemma,
)


def build_60_task_benchmark() -> list[MultiStepTask]:
    """Construct 60 deterministic multi-step tasks (20 math, 20 code, 20 physics)."""
    tasks: list[MultiStepTask] = []
    categories = ("math", "code", "physics")
    for idx in range(60):
        cat = categories[idx // 20]
        local_i = idx % 20
        task_id = f"{cat.upper()}-{local_i + 1:02d}"
        dom_order = {
            "math": ("math", "code", "physics"),
            "code": ("code", "physics", "math"),
            "physics": ("physics", "math", "code"),
        }[cat]
        lemmas: list[LemmaSpec] = []
        vals: list[int] = []
        for s_idx, dom in enumerate(dom_order):
            a = 11 + idx * 7 + s_idx * 13
            b = 19 + idx * 5 + s_idx * 17
            c = 3 + ((idx * 3 + s_idx * 11) % 19)
            exp_val = oracle_eval_lemma(dom, (a, b, c))
            lemmas.append(LemmaSpec(task_id=task_id, step_idx=s_idx, domain=dom, params=(a, b, c), expected=exp_val))
            vals.append(exp_val)
        final_exp = oracle_eval_final(vals[0], vals[1], vals[2], cat)
        tasks.append(
            MultiStepTask(
                task_id=task_id,
                category=cat,
                lemmas=(lemmas[0], lemmas[1], lemmas[2]),
                final_expected=final_exp,
            )
        )
    return tasks


def _make_honest_agents() -> list[SpecialistAgent]:
    return [
        SpecialistAgent("agent_math", {"math": 0.96, "code": 0.68, "physics": 0.62}),
        SpecialistAgent("agent_code", {"math": 0.65, "code": 0.96, "physics": 0.64}),
        SpecialistAgent("agent_phys", {"math": 0.64, "code": 0.66, "physics": 0.96}),
        SpecialistAgent("agent_synth", {"math": 0.80, "code": 0.80, "physics": 0.78}),
    ]


def run_checked_claim_arena() -> dict[str, Any]:
    """Run the 3-arm 60-task benchmark comparing isolated, unverified gossip, and checked economy."""
    tasks = build_60_task_benchmark()

    iso_agents = _make_honest_agents()
    iso_scores: dict[str, float] = {}
    for ag in iso_agents:
        solved = sum(
            1
            for t in tasks
            if oracle_eval_final(*(ag.attempt_lemma(lem, "isolated") for lem in t.lemmas), t.category)
            == t.final_expected
        )
        iso_scores[ag.name] = solved / float(len(tasks))
    isolated_mean = sum(iso_scores.values()) / float(len(iso_scores))
    isolated_best = max(iso_scores.values())

    planted_poison = {
        (tasks[idx].task_id, tasks[idx].lemmas[1].step_idx): tasks[idx].lemmas[1].expected + 137
        for idx in range(0, 60, 2)
    }

    gossip_agents = _make_honest_agents()
    gossip_board: dict[tuple[str, int], tuple[str, int]] = {}
    for t in tasks:
        for lem in t.lemmas:
            for ag in gossip_agents:
                if ag.domain_skill[lem.domain] >= 0.90:
                    gossip_board[(t.task_id, lem.step_idx)] = (ag.name, ag.attempt_lemma(lem, "gossip_pub"))
                    break
    for key, bad_val in planted_poison.items():
        gossip_board[key] = ("agent_byzantine", bad_val)

    gossip_scores: dict[str, float] = {}
    gossip_poison_consumed = 0
    for ag in gossip_agents:
        solved = 0
        for t in tasks:
            vals: list[int] = []
            for lem in t.lemmas:
                if ag.domain_skill[lem.domain] < 0.85 and (t.task_id, lem.step_idx) in gossip_board:
                    author, b_val = gossip_board[(t.task_id, lem.step_idx)]
                    if author == "agent_byzantine":
                        gossip_poison_consumed += 1
                    vals.append(b_val)
                else:
                    vals.append(ag.attempt_lemma(lem, "gossip_solve"))
            if oracle_eval_final(vals[0], vals[1], vals[2], t.category) == t.final_expected:
                solved += 1
        gossip_scores[ag.name] = solved / float(len(tasks))
    gossip_mean = sum(gossip_scores.values()) / float(len(gossip_scores))

    swarm_agents = _make_honest_agents()
    adversary = SpecialistAgent("agent_byzantine", {"math": 0.10, "code": 0.10, "physics": 0.10})
    agents_by_name = {ag.name: ag for ag in swarm_agents}
    agents_by_name[adversary.name] = adversary
    market = CheckedClaimMarketplace()

    poison_rejected = 0
    poison_accepted = 0
    for idx in range(0, 60, 2):
        t = tasks[idx]
        lem = t.lemmas[1]
        if market.submit_lemma(adversary, lem, planted_poison[(t.task_id, lem.step_idx)]):
            poison_accepted += 1
        else:
            poison_rejected += 1

    for t in tasks:
        for lem in t.lemmas:
            ranked = sorted(
                swarm_agents,
                key=lambda a: math.exp(2.0 * a.domain_skill[lem.domain]) * a.reputation,
                reverse=True,
            )
            for ag in ranked[:2]:
                if (t.task_id, lem.step_idx) in market.ledger:
                    break
                market.submit_lemma(ag, lem, ag.attempt_lemma(lem, "checked_pub"))

    tampered_total = 10
    tampered_rejected = 0
    for idx in range(tampered_total):
        rec = market.ledger[(tasks[idx].task_id, 0)]
        forged = LemmaReceipt(
            task_id=rec.task_id,
            step_idx=rec.step_idx,
            domain=rec.domain,
            author=rec.author,
            value=rec.value + 1,
            oracle_verified=True,
            receipt_sha256=rec.receipt_sha256,
        )
        if not market.verify_receipt_fail_closed(forged):
            tampered_rejected += 1

    swarm_scores: dict[str, float] = {}
    for ag in swarm_agents:
        solved = 0
        for t in tasks:
            vals = []
            for lem in t.lemmas:
                v_imp = market.fetch_verified_lemma(ag, agents_by_name, t.task_id, lem.step_idx)
                vals.append(v_imp if v_imp is not None else ag.attempt_lemma(lem, "checked_fallback"))
            if oracle_eval_final(vals[0], vals[1], vals[2], t.category) == t.final_expected:
                solved += 1
                ag.credits += 1.5
        swarm_scores[ag.name] = solved / float(len(tasks))

    swarm_mean = sum(swarm_scores.values()) / float(len(swarm_scores))
    honest_credits = {ag.name: round(ag.credits, 2) for ag in swarm_agents}
    honest_mean_credits = sum(ag.credits for ag in swarm_agents) / float(len(swarm_agents))

    ok = bool(
        (swarm_mean - isolated_mean) >= 0.20
        and (swarm_mean - isolated_best) >= 0.20
        and poison_rejected == len(planted_poison)
        and poison_accepted == 0
        and tampered_rejected == tampered_total
        and gossip_mean < swarm_mean - 0.25
        and gossip_poison_consumed > 0
        and all(c > 0.0 for c in honest_credits.values())
        and adversary.credits < 0.0
    )
    return {
        "schema": "flywheel.checked-claim-arena/1",
        "ok": ok,
        "tasks": len(tasks),
        "isolated_mean_accuracy": round(isolated_mean, 4),
        "isolated_best_accuracy": round(isolated_best, 4),
        "gossip_mean_accuracy": round(gossip_mean, 4),
        "gossip_poison_consumed": gossip_poison_consumed,
        "checked_swarm_mean_accuracy": round(swarm_mean, 4),
        "abs_gain_over_isolated_mean_pp": round((swarm_mean - isolated_mean) * 100.0, 2),
        "abs_gain_over_isolated_best_pp": round((swarm_mean - isolated_best) * 100.0, 2),
        "poison_rejected": poison_rejected,
        "poison_planted": len(planted_poison),
        "tampered_rejected": tampered_rejected,
        "tampered_planted": tampered_total,
        "honest_credits": honest_credits,
        "honest_mean_credits": round(honest_mean_credits, 2),
        "adversary_credits": round(adversary.credits, 2),
    }
