# CC-1 Phase 1B (Signed Receipts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a receipt something a stranger can verify offline on a bare interpreter, with no pip install, no network, and no trust in the author. That means an Ed25519 verifier vendored in stdlib Python, a receipt schema whose signed digest binds the claim, and a `flywheel why` that answers "why was this accepted?" from the record alone.

**Architecture:** Phase 1A produced checkers that reach verdicts. Phase 1B makes those verdicts transferable. Signing is asymmetric on purpose: HMAC would require the verifier to hold the secret, which makes third-party verification impossible, so anything exportable is Ed25519 and HMAC is local-only and stripped at pack time. The verify side is vendored (roughly 130 lines of RFC 8032 arithmetic) so the offline promise survives having no `cryptography` package. The signing side may use whatever is available, because a signer is the author and the author already has tooling; a *verifier* is a stranger and must not need any.

**Tech Stack:** Python 3.10+ stdlib only under `harness/`, enforced by `scripts/check_verifier_stdlib.py`. `int.from_bytes`, `pow`, and `hashlib.sha512` are the whole cryptographic toolkit. pytest.

## Global Constraints

Copied verbatim from `project-docs/specs/2026-07-25-certified-commons-design.md`:

- No receipt, no accept. No learned model on the accept path; an external oracle disposes.
- Verdicts are PASS, FAIL, UNDECIDED, UNVERIFIABLE. UNVERIFIABLE must say why.
- Receipts state what they do NOT prove, mechanically derived where possible.
- Records are append-only: repair adds on top, never rewrites.
- No floats in any hashed field. Integers and decimal strings only.
- Two digests, because one cannot do both jobs: a subject digest that stays verdict-free so two disagreeing verifiers remain comparable, and a claim digest that binds the verdict and is what gets signed.
- `sig_alg` is `ed25519` for anything exportable; `hmac-sha256` is local-only and stripped at pack time.
- `signed_over` is fixed in code per schema version and NEVER read from the receipt.
- Credentials: presence only, never the value. A signing key never reaches a receipt, a log, or a ledger.
- No aggregate is ever computed over the person. No trust score, ever.
- `harness/` is stdlib-only. Files stay under 300 lines; the burn-down list may only shrink.
- Voice rule: no em-dashes.
- Apache-2.0 for everything load-bearing for verification.

**Verified repository facts this plan depends on** (re-read at HEAD `85075fb`, branch `feat/cc1-phase0-ground`):

- `harness/envelope.py` `ProofEnvelope` has `content_hash()`/`content_sha256()` (subject, verdict-free) and `claim_hash()`/`claim_sha256()` (binds verdict and oracle_output_hash), plus `to_in_toto_statement()` and `to_dsse_envelope()` whose `signatures` list is currently always empty.
- `harness/criteria/registry.py` `Registry.admit(criterion) -> dict` sets `reward_eligible` from `criterion.reward_eligible()` alone; it does not consult any QA card.
- `harness/oracle_qa.py` `OracleQACard` has `passed`, `card_hash()`, `to_dict()`, `checker_source_sha256`, `false_accept_upper_bound`, `failures`.
- `harness/verdict.py` `UnverifiableReason.QA_CARD_ABSENT` already exists and is unused.
- `harness/gate.py` writes `gate_envelope.json` and `gate_report.json` and exits 0 only on `rewitness == MATCH`.

---

### Task 1: Wire the QA card into registry admission

**Files:**
- Modify: `harness/criteria/registry.py`
- Test: `tests/test_qa_gated_admission.py`

**Interfaces:**
- Consumes: `harness.oracle_qa.OracleQACard` (Phase 1A Task 7)
- Produces: `Registry.admit(criterion, *, qa_card=None)`; entry gains `qa_card_hash`, `qa_card_passed`, `false_accept_upper_bound`; `reward_ineligible_reason` may now be `QA_CARD_ABSENT` or `QA_CARD_FAILED`

**Why:** Phase 1A built both halves of "no QA card, no reward eligibility" and connected neither. The criterion knows whether its shape permits a reward and the card knows whether the checker is sound, but admission only asked the first question. Until this lands, an unmeasured checker is reward-eligible, which is the exact condition the QA gate exists to prevent.

- [ ] **Step 1: Write the failing test**

Create `tests/test_qa_gated_admission.py`:

```python
"""No QA card, no reward eligibility. Enforced at admission, not documented.

The criterion answers "does this SHAPE permit a reward" (conjunctive rule, a
domain a checker disposes). The card answers "is the checker that will grade it
actually sound". Both must hold. Phase 1A built both halves and wired neither,
so an unmeasured checker was reward-eligible: exactly the condition the QA gate
exists to prevent.
"""
import pytest

from harness.criteria.spec import Criterion, DecisionRule, Domain
from harness.criteria.registry import Registry, RegistryError
from harness.oracle_qa import qa_battery
from harness.certificates.zarankiewicz import ZarankiewiczOracle, encode
from harness.certificates.base import Coverage

FANO_LINES = [(0, 1, 2), (0, 3, 4), (0, 5, 6), (1, 3, 5),
              (1, 4, 6), (2, 3, 6), (2, 4, 5)]
FANO_EDGES = [(p, li) for li, pts in enumerate(FANO_LINES) for p in pts]


def _valid_certs():
    out = [encode(7, 7, FANO_EDGES)]
    for n in (5, 9, 13):
        out.append(encode(4, n, [(0, j) for j in range(n)]))
    return out


def _c(**kw):
    base = dict(
        criterion_id="zarankiewicz.z_2_2", version=1, family="zarankiewicz",
        generator_id="zarankiewicz.bipartite.v1", generator_version=1,
        seed_range=(0, 1024), objective_direction="maximize",
        objective_normalization="ratio_to_incumbent",
        reward_mapping={"valid_gate": True}, incumbent_source="operator_search",
        scope_bounds={"m_max": 40}, decision_rule=DecisionRule.CONJUNCTIVE,
        domain=Domain.CONSTRUCTIVE, license_id="Apache-2.0")
    base.update(kw)
    return Criterion(**base)


def test_a_criterion_admitted_without_a_card_is_not_reward_eligible(tmp_path):
    r = Registry(tmp_path / "r.json")
    entry = r.admit(_c())
    assert entry["reward_eligible"] is False
    assert entry["reward_ineligible_reason"] == "QA_CARD_ABSENT"


def test_a_passing_card_makes_a_clean_criterion_reward_eligible(tmp_path):
    r = Registry(tmp_path / "r.json")
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    assert card.passed is True
    entry = r.admit(_c(), qa_card=card)
    assert entry["reward_eligible"] is True
    assert entry["reward_ineligible_reason"] == ""


def test_a_failing_card_blocks_reward_eligibility(tmp_path):
    class _Lax(ZarankiewiczOracle):
        def check(self, cert):
            return True, "accepts anything", Coverage(
                True, True, "1", "complete", None)

    r = Registry(tmp_path / "r.json")
    card = qa_battery(_Lax(), _valid_certs(), seed=5)
    assert card.passed is False
    entry = r.admit(_c(), qa_card=card)
    assert entry["reward_eligible"] is False
    assert entry["reward_ineligible_reason"] == "QA_CARD_FAILED"


def test_the_criterion_shape_is_checked_before_the_card(tmp_path):
    # An interpretive criterion with a perfect card is still refused, and the
    # reason names the domain. The more fundamental refusal is the one a reader
    # should see.
    r = Registry(tmp_path / "r.json")
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    entry = r.admit(_c(criterion_id="poetry.tone", family="poetry",
                       domain=Domain.INTERPRETIVE), qa_card=card)
    assert entry["reward_eligible"] is False
    assert entry["reward_ineligible_reason"] == "INTERPRETIVE_DOMAIN"


def test_the_entry_records_the_card_hash_and_the_bound(tmp_path):
    r = Registry(tmp_path / "r.json")
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    entry = r.admit(_c(), qa_card=card)
    assert entry["qa_card_hash"] == card.card_hash()
    assert entry["qa_card_passed"] is True
    # A decimal string, never a float, because it lands in a hashed record.
    assert isinstance(entry["false_accept_upper_bound"], str)
    assert float(entry["false_accept_upper_bound"]) < 0.05


def test_reward_eligible_ids_respects_the_card(tmp_path):
    r = Registry(tmp_path / "r.json")
    r.admit(_c())                                    # no card
    assert r.reward_eligible_ids() == []
    r2 = Registry(tmp_path / "r2.json")
    r2.admit(_c(), qa_card=qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5))
    assert r2.reward_eligible_ids() == ["zarankiewicz.z_2_2"]


def test_a_card_for_the_wrong_family_is_refused(tmp_path):
    # A card grades a specific checker. Attaching one from another family would
    # let a sound checker vouch for an unmeasured one.
    r = Registry(tmp_path / "r.json")
    card = qa_battery(ZarankiewiczOracle(), _valid_certs(), seed=5)
    with pytest.raises(RegistryError):
        r.admit(_c(criterion_id="other.thing", family="something_else"),
                qa_card=card)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qa_gated_admission.py -q`
Expected: FAIL. `Registry.admit()` rejects the `qa_card` keyword.

- [ ] **Step 3: Write minimal implementation**

In `harness/criteria/registry.py`, replace the eligibility block inside `admit` (the three lines from `ok, reason = criterion.reward_eligible()` through the `entry = {` dict) with:

```python
        # Two questions, both of which must hold. The criterion answers whether
        # this SHAPE may mint a reward; the card answers whether the checker that
        # will grade it is actually sound. Phase 1A built both halves and wired
        # neither, so an unmeasured checker was reward-eligible.
        ok, reason = criterion.reward_eligible()
        if ok:
            if qa_card is None:
                ok, reason = False, "QA_CARD_ABSENT"
            elif getattr(qa_card, "family", None) not in (None, criterion.family):
                raise RegistryError(
                    f"qa card grades family {qa_card.family!r}, criterion is "
                    f"{criterion.family!r}: a card from another family would let "
                    "a sound checker vouch for an unmeasured one")
            elif not qa_card.passed:
                ok, reason = False, "QA_CARD_FAILED"

        entry = {
            "criterion_id": criterion.criterion_id,
            "version": criterion.version,
            "criterion_sha256": digest,
            "parent_sha256": criterion.parent_sha256,
            "change_reason": criterion.change_reason,
            "status": "live",
            "reward_eligible": ok,
            "reward_ineligible_reason": "" if ok else reason,
            "qa_card_hash": qa_card.card_hash() if qa_card else "",
            "qa_card_passed": bool(qa_card.passed) if qa_card else False,
            "false_accept_upper_bound": (
                f"{qa_card.false_accept_upper_bound:.6f}" if qa_card else ""),
            "criterion": criterion.to_dict(),
            "invalidation": None,
        }
```

and change the signature:

```python
    def admit(self, criterion: Criterion, *, qa_card=None) -> dict:
```

The family check must run before the `passed` check, so a mismatched card raises rather than silently downgrading eligibility.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_qa_gated_admission.py tests/test_criterion_registry.py -q`
Expected: the new file passes. `test_criterion_registry.py` will now FAIL on its eligibility assertions, because admission without a card is no longer reward-eligible. That is the intended behaviour change: update those assertions to pass a card or to expect `QA_CARD_ABSENT`, and record the change in the commit message.

- [ ] **Step 5: Gate checks**

Run: `python scripts/check_verifier_stdlib.py && python scripts/check_file_gate.py`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add harness/criteria/registry.py tests/test_qa_gated_admission.py tests/test_criterion_registry.py
git commit -m "feat(criteria): no QA card, no reward eligibility, enforced at admission"
```

---

### Remaining Phase 1B tasks

Written out when Task 1 lands, so their interfaces are real rather than predicted.

- **Task 2: vendored Ed25519 verify-only** (`harness/ed25519_verify.py`). RFC 8032 verification in stdlib arithmetic: point decompression, scalar multiplication by double-and-add, the `[8][S]B = [8]R + [8][k]A` check. Verify only, never sign, because a verifier must run anywhere and a signer is the author who already has tooling. Test vectors from RFC 8032 section 7.1, plus a mutated-signature battery, plus the small-order and non-canonical encodings that trip naive implementations.
- **Task 3: receipt v2** (`harness/receipt.py`). The schema from spec section 5: two digests, mandatory denominators, nominal evidence kinds, mechanically derived `does_not_prove`, typed invalidation, `signed_over` fixed in code. No floats in any hashed field.
- **Task 4: sign and verify end to end** (`harness/receipt_sign.py`, `flywheel verify`). A signed receipt a stranger checks with the vendored verifier and nothing else. HMAC is local-only and stripped at pack time.
- **Task 5: `flywheel why`** (`harness/why.py`). Answers "why was this accepted?" from the record alone, in one command, offline. Per the practitioner contract this must be the cheapest action available, so it takes a receipt id or a hash prefix and needs no flags.

## Self-Review

**Spec coverage.** Phase 1B covers the signing and receipt half of spec Layer 2. It does NOT cover the ledger's inclusion and consistency proofs, the signed tree head and its external anchor, bundle pack and verify, or the contest channel. Those are Phase 1C. Splitting there is deliberate: a signed receipt is independently useful and independently testable, while a ledger without signed entries would be a hash chain over unauthenticated claims.

**Placeholder scan.** Task 1 carries complete code and exact commands, including the honest warning that it deliberately breaks existing registry assertions. Tasks 2 through 5 are specified rather than written, stated as a scoping decision.

**Type consistency.** `OracleQACard.passed`, `.card_hash()`, `.family`, `.false_accept_upper_bound` in Task 1 all match the definitions committed in Phase 1A Task 7. `Registry.admit` keeps its positional first argument, so existing calls that pass no card keep working and simply become reward-ineligible, which is the intended default.
