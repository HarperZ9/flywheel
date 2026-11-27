# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""J14 Checked-Claim Economy: Oracle-Gated SHA-256 Lemma Marketplace.

Implements canonical SHA-256 oracle-sealed lemma receipts, independent math/code/
physics verification oracles, specialist peer models, and ECO-001 honest-work
vs faking economic payoffs with fail-closed receipt verification.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math


@dataclass(frozen=True)
class LemmaSpec:
    task_id: str
    step_idx: int
    domain: str
    params: tuple[int, int, int]
    expected: int


@dataclass(frozen=True)
class MultiStepTask:
    task_id: str
    category: str
    lemmas: tuple[LemmaSpec, LemmaSpec, LemmaSpec]
    final_expected: int


@dataclass(frozen=True)
class LemmaReceipt:
    task_id: str
    step_idx: int
    domain: str
    author: str
    value: int
    oracle_verified: bool
    receipt_sha256: str


def canonical_receipt_hash(
    task_id: str,
    step_idx: int,
    domain: str,
    author: str,
    value: int,
    oracle_verified: bool,
) -> str:
    """Compute canonical SHA-256 commitment over a verified lemma claim."""
    payload = json.dumps(
        {
            "author": author,
            "domain": domain,
            "oracle_verified": oracle_verified,
            "step_idx": step_idx,
            "task_id": task_id,
            "value": value,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def oracle_eval_lemma(domain: str, params: tuple[int, int, int]) -> int:
    """Deterministic independent domain oracle for math, code, and physics sub-lemmas."""
    a, b, c = params
    if domain == "math":
        q = (a * a + 3 * a * b + b * b) % 997
        return int(q + math.gcd(a + 17, b + 29) * c)
    if domain == "code":
        acc = (a * 31 + b * 17 + c * 13) & 0xFFFF
        for k in range(8):
            acc = ((acc << 3) ^ (acc >> 2) ^ (k * 97 + a + b)) & 0xFFFF
        arr = [(a + i * b + i * i * c) % 11 for i in range(5)]
        invs = sum(1 for i in range(5) for j in range(i + 1, 5) if arr[i] > arr[j])
        return int((acc % 1009) + invs * 7)
    if domain == "physics":
        m = 2 + (a % 7)
        v = 3 + (b % 11)
        k_spring = 4 + (c % 9)
        x = 1 + ((a + b) % 8)
        h = 2 + ((b + c) % 10)
        g_milli = 981
        return int(100 * (m * v * v + k_spring * x * x) + (m * g_milli * h) // 5)
    raise ValueError(f"UNKNOWN_DOMAIN:{domain}")


def oracle_eval_final(v0: int, v1: int, v2: int, category: str) -> int:
    """Deterministic synthesis oracle combining three sub-lemma values."""
    if category == "math":
        return int((3 * v0 + 5 * v1 + 7 * v2) % 100003)
    if category == "code":
        return int(((v0 ^ (v1 << 1)) + 11 * v2) % 100003)
    if category == "physics":
        return int((v0 + 2 * v1 + 3 * v2 + (v0 * v2) % 991) % 100003)
    raise ValueError(f"UNKNOWN_CATEGORY:{category}")


def _det_unit(seed_key: str) -> float:
    digest = hashlib.sha256(seed_key.encode("utf-8")).digest()
    return float(int.from_bytes(digest[:8], "big")) / float(1 << 64)


class SpecialistAgent:
    """Deterministic specialist peer agent with domain competence and ECO-001 credit balance."""

    def __init__(self, name: str, domain_skill: dict[str, float]) -> None:
        self.name = name
        self.domain_skill = dict(domain_skill)
        self.credits = 0.0
        self.reputation = 1.0
        self.published_verified = 0
        self.rejected_claims = 0

    def attempt_lemma(self, lemma: LemmaSpec, arm_tag: str) -> int:
        p_ok = self.domain_skill[lemma.domain]
        u = _det_unit(f"{arm_tag}:{self.name}:{lemma.task_id}:{lemma.step_idx}")
        if u < p_ok:
            return lemma.expected
        return lemma.expected + 1 + int(u * 13)


class CheckedClaimMarketplace:
    """Oracle-gated SHA-256 sealed lemma marketplace enforcing ECO-001 payoffs."""

    REWARD_PUBLISH = 3.0
    COST_HONEST = 1.0
    COST_FAKE = 0.2
    FINE_CAUGHT = 5.0
    ROYALTY_REUSE = 0.75
    IMPORT_FEE = 0.25

    def __init__(self) -> None:
        self.ledger: dict[tuple[str, int], LemmaReceipt] = {}
        self.total_submissions = 0
        self.verified_accepted = 0
        self.false_rejected = 0
        self.tampered_rejected = 0

    def submit_lemma(self, agent: SpecialistAgent, lemma: LemmaSpec, candidate_value: int) -> bool:
        self.total_submissions += 1
        truth = oracle_eval_lemma(lemma.domain, lemma.params)
        if candidate_value != truth:
            self.false_rejected += 1
            agent.rejected_claims += 1
            agent.credits -= self.COST_FAKE + self.FINE_CAUGHT
            agent.reputation = max(0.05, agent.reputation * 0.65)
            return False

        r_hash = canonical_receipt_hash(
            lemma.task_id, lemma.step_idx, lemma.domain, agent.name, candidate_value, True
        )
        key = (lemma.task_id, lemma.step_idx)
        if key not in self.ledger:
            self.ledger[key] = LemmaReceipt(
                task_id=lemma.task_id,
                step_idx=lemma.step_idx,
                domain=lemma.domain,
                author=agent.name,
                value=candidate_value,
                oracle_verified=True,
                receipt_sha256=r_hash,
            )
            self.verified_accepted += 1
            agent.published_verified += 1
            agent.credits += self.REWARD_PUBLISH - self.COST_HONEST
            agent.reputation = min(3.0, agent.reputation + 0.05)
        return True

    def verify_receipt_fail_closed(self, receipt: LemmaReceipt) -> bool:
        if not receipt.oracle_verified:
            self.tampered_rejected += 1
            return False
        expected = canonical_receipt_hash(
            receipt.task_id,
            receipt.step_idx,
            receipt.domain,
            receipt.author,
            receipt.value,
            receipt.oracle_verified,
        )
        if receipt.receipt_sha256 != expected:
            self.tampered_rejected += 1
            return False
        return True

    def fetch_verified_lemma(
        self,
        consumer: SpecialistAgent,
        agents_by_name: dict[str, SpecialistAgent],
        task_id: str,
        step_idx: int,
    ) -> int | None:
        rec = self.ledger.get((task_id, step_idx))
        if rec is None or not self.verify_receipt_fail_closed(rec):
            return None
        if rec.author != consumer.name:
            consumer.credits -= self.IMPORT_FEE
            agents_by_name[rec.author].credits += self.ROYALTY_REUSE
        return rec.value
