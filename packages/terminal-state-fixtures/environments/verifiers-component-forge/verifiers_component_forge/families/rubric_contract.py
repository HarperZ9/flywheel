"""rubric-contract family: scoring contracts and their reference modules.

A CONTRACT is an ordered table of named criteria with an explicit weight
vector (always exactly one zero-weight diagnostic, optionally one negative
weight), plus two normative rules:

- ERROR RULE. A criterion that reads ``info`` and finds its key missing or
  malformed evaluates to 0.0. Never an exception.
- EXCLUSION RULE (when the contract enables it). When ``info["excluded"]`` is
  exactly ``True``, every WEIGHTED criterion evaluates to 0.0; zero-weight
  diagnostics still compute their real value. When the contract does not
  enable the rule, the flag is ordinary data and must be ignored.

Aggregation is the raw weighted sum through the library's own machinery --
no normalization, which is precisely the classic mistake the family exists
to catch.

The single source of truth is ``reference_module_source``: the module text an
ideal agent would emit. The generator executes THAT source through the real
``verifiers`` machinery to freeze expectations, the discrimination tests run
the same source through the child driver, and the prompt's worked rows are
computed from it, so contract prose, oracle, and exemplar can never drift
apart.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---- criterion pool ---------------------------------------------------------
# kind -> (needs_param, body template). Bodies are emitted into the reference
# module; ``{excl}`` is replaced with the exclusion guard for weighted criteria
# under contracts that enable the rule, or "" otherwise.

_BODIES = {
    "exact": "    {excl}return 1.0 if completion == answer else 0.0",
    "contains": "    {excl}return 1.0 if answer in completion else 0.0",
    "len_under": "    {excl}return 1.0 if len(completion) <= {param} else 0.0",
    "starts_upper": "    {excl}return 1.0 if completion[:1].isupper() else 0.0",
    "info_ratio": (
        "    {excl}try:\n"
        "        value = float(info[{param!r}])\n"
        "    except (KeyError, TypeError, ValueError):\n"
        "        return 0.0\n"
        "    return min(max(value, 0.0), 1.0)"
    ),
    "info_flag": (
        "    {excl}try:\n"
        "        return 1.0 if info[{param!r}] else 0.0\n"
        "    except (KeyError, TypeError):\n"
        "        return 0.0"
    ),
    # zero-weight diagnostics: never excluded, never guarded
    "len_metric": "    return float(len(completion))",
    "word_metric": "    return float(len(completion.split()))",
}

_EXCL_GUARD = 'if info.get("excluded") is True:\n        return 0.0\n    '


@dataclass(frozen=True)
class Criterion:
    name: str
    kind: str
    param: str | int | None = None


@dataclass(frozen=True)
class Contract:
    table_ix: int
    criteria: tuple[Criterion, ...]
    weights: tuple[float, ...]
    exclusion: bool
    negative: bool

    @property
    def variant_id(self) -> str:
        return (
            f"rc-{self.table_ix:02d}-excl{int(self.exclusion)}-neg{int(self.negative)}"
        )

    @property
    def effective_weights(self) -> tuple[float, ...]:
        if not self.negative:
            return self.weights
        w = list(self.weights)
        w[1] = -w[1]  # the second criterion carries the negative weight
        return tuple(w)


# ---- the 24 fixed tables ----------------------------------------------------
# (criterion spec..., weights) -- the LAST criterion is always the 0-weight
# diagnostic. Weighted criteria count 2..5. Names are stable and readable.

_C = Criterion
_TABLE_SPECS: tuple[tuple[tuple[Criterion, ...], tuple[float, ...]], ...] = (
    # size 3 (2 weighted + diagnostic)
    (
        (
            _C("exact_match", "exact"),
            _C("brevity", "len_under", 24),
            _C("length_chars", "len_metric"),
        ),
        (0.7, 0.3, 0.0),
    ),
    (
        (
            _C("contains_answer", "contains"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("word_count", "word_metric"),
        ),
        (0.6, 0.4, 0.0),
    ),
    (
        (
            _C("exact_match", "exact"),
            _C("used_tool", "info_flag", "tool_used"),
            _C("length_chars", "len_metric"),
        ),
        (0.8, 0.2, 0.0),
    ),
    (
        (
            _C("starts_capitalized", "starts_upper"),
            _C("exact_match", "exact"),
            _C("word_count", "word_metric"),
        ),
        (0.25, 0.75, 0.0),
    ),
    (
        (
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("brevity", "len_under", 40),
            _C("length_chars", "len_metric"),
        ),
        (0.5, 0.5, 0.0),
    ),
    (
        (
            _C("used_tool", "info_flag", "tool_used"),
            _C("contains_answer", "contains"),
            _C("word_count", "word_metric"),
        ),
        (0.35, 0.65, 0.0),
    ),
    # size 4
    (
        (
            _C("exact_match", "exact"),
            _C("brevity", "len_under", 32),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("length_chars", "len_metric"),
        ),
        (0.5, 0.2, 0.3, 0.0),
    ),
    (
        (
            _C("contains_answer", "contains"),
            _C("starts_capitalized", "starts_upper"),
            _C("used_tool", "info_flag", "tool_used"),
            _C("word_count", "word_metric"),
        ),
        (0.45, 0.15, 0.4, 0.0),
    ),
    (
        (
            _C("exact_match", "exact"),
            _C("contains_answer", "contains"),
            _C("brevity", "len_under", 24),
            _C("length_chars", "len_metric"),
        ),
        (0.6, 0.25, 0.15, 0.0),
    ),
    (
        (
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("used_tool", "info_flag", "tool_used"),
            _C("exact_match", "exact"),
            _C("word_count", "word_metric"),
        ),
        (0.3, 0.3, 0.4, 0.0),
    ),
    (
        (
            _C("brevity", "len_under", 48),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("starts_capitalized", "starts_upper"),
            _C("length_chars", "len_metric"),
        ),
        (0.4, 0.35, 0.25, 0.0),
    ),
    (
        (
            _C("used_tool", "info_flag", "tool_used"),
            _C("exact_match", "exact"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("word_count", "word_metric"),
        ),
        (0.2, 0.55, 0.25, 0.0),
    ),
    # size 5
    (
        (
            _C("exact_match", "exact"),
            _C("contains_answer", "contains"),
            _C("brevity", "len_under", 32),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("length_chars", "len_metric"),
        ),
        (0.4, 0.2, 0.15, 0.25, 0.0),
    ),
    (
        (
            _C("starts_capitalized", "starts_upper"),
            _C("used_tool", "info_flag", "tool_used"),
            _C("exact_match", "exact"),
            _C("brevity", "len_under", 24),
            _C("word_count", "word_metric"),
        ),
        (0.1, 0.3, 0.4, 0.2, 0.0),
    ),
    (
        (
            _C("contains_answer", "contains"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("used_tool", "info_flag", "tool_used"),
            _C("starts_capitalized", "starts_upper"),
            _C("length_chars", "len_metric"),
        ),
        (0.35, 0.25, 0.25, 0.15, 0.0),
    ),
    (
        (
            _C("exact_match", "exact"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("brevity", "len_under", 40),
            _C("used_tool", "info_flag", "tool_used"),
            _C("word_count", "word_metric"),
        ),
        (0.45, 0.2, 0.15, 0.2, 0.0),
    ),
    (
        (
            _C("brevity", "len_under", 64),
            _C("exact_match", "exact"),
            _C("contains_answer", "contains"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("length_chars", "len_metric"),
        ),
        (0.15, 0.45, 0.2, 0.2, 0.0),
    ),
    (
        (
            _C("used_tool", "info_flag", "tool_used"),
            _C("starts_capitalized", "starts_upper"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("exact_match", "exact"),
            _C("word_count", "word_metric"),
        ),
        (0.25, 0.1, 0.25, 0.4, 0.0),
    ),
    # size 6
    (
        (
            _C("exact_match", "exact"),
            _C("contains_answer", "contains"),
            _C("brevity", "len_under", 32),
            _C("starts_capitalized", "starts_upper"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("length_chars", "len_metric"),
        ),
        (0.3, 0.2, 0.15, 0.1, 0.25, 0.0),
    ),
    (
        (
            _C("contains_answer", "contains"),
            _C("used_tool", "info_flag", "tool_used"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("exact_match", "exact"),
            _C("brevity", "len_under", 24),
            _C("word_count", "word_metric"),
        ),
        (0.2, 0.15, 0.2, 0.3, 0.15, 0.0),
    ),
    (
        (
            _C("starts_capitalized", "starts_upper"),
            _C("brevity", "len_under", 48),
            _C("exact_match", "exact"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("used_tool", "info_flag", "tool_used"),
            _C("length_chars", "len_metric"),
        ),
        (0.1, 0.2, 0.35, 0.2, 0.15, 0.0),
    ),
    (
        (
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("exact_match", "exact"),
            _C("used_tool", "info_flag", "tool_used"),
            _C("contains_answer", "contains"),
            _C("starts_capitalized", "starts_upper"),
            _C("word_count", "word_metric"),
        ),
        (0.25, 0.3, 0.2, 0.15, 0.1, 0.0),
    ),
    (
        (
            _C("brevity", "len_under", 40),
            _C("contains_answer", "contains"),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("starts_capitalized", "starts_upper"),
            _C("exact_match", "exact"),
            _C("length_chars", "len_metric"),
        ),
        (0.15, 0.2, 0.2, 0.1, 0.35, 0.0),
    ),
    (
        (
            _C("used_tool", "info_flag", "tool_used"),
            _C("exact_match", "exact"),
            _C("brevity", "len_under", 64),
            _C("cited_confidence", "info_ratio", "confidence"),
            _C("contains_answer", "contains"),
            _C("word_count", "word_metric"),
        ),
        (0.2, 0.35, 0.1, 0.2, 0.15, 0.0),
    ),
)


def all_contracts() -> list[Contract]:
    out = []
    for ix, (criteria, weights) in enumerate(_TABLE_SPECS):
        for exclusion in (False, True):
            for negative in (False, True):
                out.append(Contract(ix, criteria, weights, exclusion, negative))
    return out


# ---- reference module -------------------------------------------------------


def reference_module_source(contract: Contract) -> str:
    """The module an ideal agent would emit for this contract."""
    parts = [
        "import verifiers as vf",
        "from datasets import Dataset",
        "",
    ]
    for criterion, weight in zip(contract.criteria, contract.effective_weights):
        guard = _EXCL_GUARD if (contract.exclusion and weight != 0.0) else ""
        body = _BODIES[criterion.kind]
        if "{param" in body:
            body = body.replace("{param!r}", repr(criterion.param)).replace(
                "{param}", repr(criterion.param)
            )
        body = body.replace("{excl}", guard)
        parts.append(f"def {criterion.name}(completion, answer, info, **kwargs):")
        parts.append(body)
        parts.append("")
    names = ", ".join(c.name for c in contract.criteria)
    weights = ", ".join(repr(w) for w in contract.effective_weights)
    parts += [
        "def load_environment(**kwargs):",
        f"    rubric = vf.Rubric(funcs=[{names}], weights=[{weights}])",
        '    dataset = Dataset.from_list([{"question": "stub", "answer": "stub"}])',
        "    return vf.SingleTurnEnv(dataset=dataset, rubric=rubric, **kwargs)",
        "",
    ]
    return "\n".join(parts)
