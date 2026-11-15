"""rubric-repair family: broken rubric wirings and their mutation operators.

An INSTANCE is one seed contract (drawn from the rubric-contract tables) with
one mutation operator applied to its reference module source. The agent sees
the broken module, the normative contract (REWARD.md prose), one frozen
symptom, and three visible expected rows; it must return the repaired module.

Every operator is an exact-substring transform of the GENERATED reference
source, so a mutation is information-preserving by construction: the correct
behavior is always re-derivable from the contract prose alone, and the broken
module differs from the reference in exactly one stated behavior. The
generator applies a kill-check before shipping: a mutant ships only when it
flips at least two battery fixtures, so one flip can be shown as the visible
symptom while at least one more stays hidden and scored.

Credit concentrates on the kill set: hidden fixtures where broken and
reference outputs disagree carry KILL_SHARE of the weight, agreeing fixtures
carry the rest as a regression share, so the verbatim broken module scores at
most the regression share and an over-eager rewrite that breaks untouched
semantics loses regression credit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rubric_contract import _EXCL_GUARD, Contract, Criterion, all_contracts

KILL_SHARE = 0.85
REGRESSION_SHARE = 0.15

# ---- the 8 seeds ------------------------------------------------------------
# (table_ix, exclusion, negative), chosen so every criterion kind, the
# exclusion rule, and the negative weight each appear in several seeds.

SEED_SPECS: tuple[tuple[int, bool, bool], ...] = (
    (8, False, False),
    (9, True, False),
    (12, False, True),
    (18, True, True),
    (19, True, False),
    (15, False, True),
    (23, True, False),
    (13, False, False),
)


def seed_contracts() -> tuple[Contract, ...]:
    by_key = {(c.table_ix, c.exclusion, c.negative): c for c in all_contracts()}
    return tuple(by_key[spec] for spec in SEED_SPECS)


# ---- operators --------------------------------------------------------------


def _kinds(contract: Contract) -> dict[str, Criterion]:
    return {c.kind: c for c in contract.criteria}


def _weights_literal(weights: tuple[float, ...]) -> str:
    return "weights=[" + ", ".join(repr(w) for w in weights) + "]"


def _swap_weights(source: str, contract: Contract, new: tuple[float, ...]) -> str:
    old_lit = _weights_literal(contract.effective_weights)
    if old_lit not in source:
        raise AssertionError(f"weights literal missing: {old_lit}")
    return source.replace(old_lit, _weights_literal(new))


def _replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise AssertionError(f"mutation anchor missing: {old!r}")
    return source.replace(old, new)


def _mut_weights_normalized(source: str, c: Contract) -> str:
    n = len(c.criteria)
    return _swap_weights(source, c, tuple(w / n for w in c.effective_weights))


def _mut_weights_swapped(source: str, c: Contract) -> str:
    w = list(c.effective_weights)
    w[0], w[1] = w[1], w[0]
    return _swap_weights(source, c, tuple(w))


def _mut_negative_flipped(source: str, c: Contract) -> str:
    return _swap_weights(source, c, tuple(abs(w) for w in c.effective_weights))


def _mut_diagnostic_dropped(source: str, c: Contract) -> str:
    names = [crit.name for crit in c.criteria]
    source = _replace_once(
        source,
        "funcs=[" + ", ".join(names) + "]",
        "funcs=[" + ", ".join(names[:-1]) + "]",
    )
    return _replace_once(
        source,
        _weights_literal(c.effective_weights),
        _weights_literal(c.effective_weights[:-1]),
    )


def _mut_exclusion_inverted(source: str, c: Contract) -> str:
    return _replace_once(
        source,
        'if info.get("excluded") is True:',
        'if info.get("excluded") is not True:',
    )


def _mut_exclusion_ignored(source: str, c: Contract) -> str:
    return _replace_once(source, _EXCL_GUARD, "")


def _mut_exclusion_on_diagnostic(source: str, c: Contract) -> str:
    diag = c.criteria[-1].name
    head = f"def {diag}(completion, answer, info, **kwargs):\n    return "
    return _replace_once(
        source,
        head,
        f"def {diag}(completion, answer, info, **kwargs):\n    "
        + _EXCL_GUARD
        + "return ",
    )


def _mut_boundary_strict(source: str, c: Contract) -> str:
    n = _kinds(c)["len_under"].param
    return _replace_once(
        source, f"len(completion) <= {n!r}", f"len(completion) < {n!r}"
    )


def _mut_clamp_dropped(source: str, c: Contract) -> str:
    return _replace_once(
        source, "    return min(max(value, 0.0), 1.0)", "    return value"
    )


def _mut_guard_dropped(source: str, c: Contract) -> str:
    key = _kinds(c)["info_ratio"].param
    old = (
        "    try:\n"
        f"        value = float(info[{key!r}])\n"
        "    except (KeyError, TypeError, ValueError):\n"
        "        return 0.0\n"
        "    return min(max(value, 0.0), 1.0)"
    )
    new = f"    value = float(info[{key!r}])\n    return min(max(value, 0.0), 1.0)"
    return _replace_once(source, old, new)


def _mut_flag_identity(source: str, c: Contract) -> str:
    key = _kinds(c)["info_flag"].param
    return _replace_once(
        source,
        f"return 1.0 if info[{key!r}] else 0.0",
        f"return 1.0 if info[{key!r}] is True else 0.0",
    )


def _mut_contains_equality(source: str, c: Contract) -> str:
    return _replace_once(
        source,
        "1.0 if answer in completion else 0.0",
        "1.0 if completion == answer else 0.0",
    )


def _mut_exact_casefold(source: str, c: Contract) -> str:
    return _replace_once(
        source,
        "1.0 if completion == answer else 0.0",
        "1.0 if completion.lower() == answer.lower() else 0.0",
    )


def _mut_exact_strip(source: str, c: Contract) -> str:
    return _replace_once(
        source,
        "1.0 if completion == answer else 0.0",
        "1.0 if completion.strip() == answer else 0.0",
    )


@dataclass(frozen=True)
class Operator:
    name: str
    gate_breaking: bool  # wrong funcs/weights vector: the structural gate zeroes it

    def applies(self, c: Contract) -> bool:
        kinds = _kinds(c)
        if self.name == "weights-swapped":
            return c.effective_weights[0] != c.effective_weights[1]
        if self.name == "negative-weight-flipped":
            return c.negative
        if self.name.startswith("exclusion-"):
            return c.exclusion
        if self.name == "boundary-strict":
            return "len_under" in kinds
        if self.name in ("clamp-dropped", "guard-dropped"):
            return "info_ratio" in kinds
        if self.name == "flag-identity":
            return "info_flag" in kinds
        if self.name == "contains-equality":
            return "contains" in kinds
        if self.name in ("exact-casefold", "exact-strip"):
            return "exact" in kinds
        return True

    def mutate(self, source: str, c: Contract) -> str:
        broken = _MUTATORS[self.name](source, c)
        if broken == source:
            raise AssertionError(f"{self.name}: mutation was a no-op")
        compile(broken, f"<broken:{self.name}>", "exec")  # must stay importable
        return broken


_MUTATORS = {
    "weights-normalized": _mut_weights_normalized,
    "weights-swapped": _mut_weights_swapped,
    "negative-weight-flipped": _mut_negative_flipped,
    "diagnostic-dropped": _mut_diagnostic_dropped,
    "exclusion-inverted": _mut_exclusion_inverted,
    "exclusion-ignored": _mut_exclusion_ignored,
    "exclusion-on-diagnostic": _mut_exclusion_on_diagnostic,
    "boundary-strict": _mut_boundary_strict,
    "clamp-dropped": _mut_clamp_dropped,
    "guard-dropped": _mut_guard_dropped,
    "flag-identity": _mut_flag_identity,
    "contains-equality": _mut_contains_equality,
    "exact-casefold": _mut_exact_casefold,
    "exact-strip": _mut_exact_strip,
}

OPERATORS: tuple[Operator, ...] = (
    Operator("weights-normalized", True),
    Operator("weights-swapped", True),
    Operator("negative-weight-flipped", True),
    Operator("diagnostic-dropped", True),
    Operator("exclusion-inverted", False),
    Operator("exclusion-ignored", False),
    Operator("exclusion-on-diagnostic", False),
    Operator("boundary-strict", False),
    Operator("clamp-dropped", False),
    Operator("guard-dropped", False),
    Operator("flag-identity", False),
    Operator("contains-equality", False),
    Operator("exact-casefold", False),
    Operator("exact-strip", False),
)


@dataclass(frozen=True)
class Mutant:
    seed_ix: int
    contract: Contract
    operator: Operator
    broken_source: str

    @property
    def instance_id(self) -> str:
        return f"rr-s{self.seed_ix}-{self.operator.name}"


def all_mutants() -> list[Mutant]:
    """Every applicable (seed, operator) pair, before the kill-check."""
    from .rubric_contract import reference_module_source

    out = []
    for seed_ix, contract in enumerate(seed_contracts()):
        source = reference_module_source(contract)
        for op in OPERATORS:
            if op.applies(contract):
                out.append(Mutant(seed_ix, contract, op, op.mutate(source, contract)))
    return out
