"""verifiers-component-forge: write and repair verifiers components against
normative behavioral contracts, scored by terminal state.

The agent receives a fully normative contract and must emit a Python module;
scoring executes that module in an isolated child interpreter over hidden
frozen probes and compares terminal state against reference-derived
expectations. No judge model, no network, and the oracle never enters the
child process. See DESIGN.md for the family designs and the freeze pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import verifiers as vf
from datasets import Dataset

from . import scoring
from .families.parser_contract import Variant, scope_text

_DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_frozen(name: str) -> dict:
    return json.loads((_DATA_DIR / name).read_text(encoding="utf-8"))


class LastPythonFenceParser(vf.Parser):
    """The environment's own completion parser: from the LAST ```python opener
    to the LAST ``` closer in the reply, all messages joined.

    Deliberately NOT the contract's own non-greedy fence rung: an honest
    solution frequently contains triple-backtick literals (docstrings quoting
    the contract, regexes implementing fence rungs), and a first-close parser
    would truncate it mid-module. Last-opener-to-last-closer survives that,
    and the emission protocol documents it."""

    def parse_answer(self, completion) -> str | None:  # type: ignore[override]
        text = scope_text(completion, "joined")
        opener = text.rfind("```python\n")
        if opener == -1:
            return None
        start = opener + len("```python\n")
        closer = text.rfind("```")
        if closer <= start:
            return None
        content = text[start:closer].strip()
        return content or None


def load_environment(families: list[str] | None = None, **kwargs) -> vf.Environment:
    """Build the environment. ``families`` optionally restricts the dataset
    to a subset of task families (e.g. ``["referee-protocol"]``), for
    per-family evaluation and RL runs; the default serves all of them."""
    frozen = {
        "parser-contract": _load_frozen("parser_contract.json"),
        "rubric-contract": _load_frozen("rubric_contract.json"),
        "rubric-repair": _load_frozen("rubric_repair.json"),
        "referee-protocol": _load_frozen("referee_protocol.json"),
        "redaction-contract": _load_frozen("redaction_contract.json"),
    }
    frozen_parser = frozen["parser-contract"]
    frozen_rubric = frozen["rubric-contract"]
    frozen_repair = frozen["rubric-repair"]
    frozen_referee = frozen["referee-protocol"]
    frozen_redaction = frozen["redaction-contract"]
    parser = LastPythonFenceParser()

    rows = []
    from .families.parser_contract_prompt import render_prompt
    from .families.redaction_contract import RedactionVariant
    from .families.redaction_contract_prompt import (
        render_prompt as render_redaction_prompt,
    )
    from .families.referee_protocol_prompt import render_prompt as render_referee_prompt
    from .families.rubric_contract_prompt import render_prompt as render_rubric_prompt
    from .families.rubric_repair_prompt import render_prompt as render_repair_prompt

    for variant_id in sorted(frozen_parser):
        entry = frozen_parser[variant_id]
        v = entry["variant"]
        variant = Variant(
            tuple(v["ladder"]), v["scope"], v["think_strip"], v["empty_hit"]
        )
        rows.append(
            {
                "question": render_prompt(variant),
                "answer": variant_id,
                "info": {"family": "parser-contract", "variant_id": variant_id},
            }
        )
    for variant_id in sorted(frozen_rubric):
        entry = frozen_rubric[variant_id]
        rows.append(
            {
                "question": render_rubric_prompt(entry["contract"], entry["worked"]),
                "answer": variant_id,
                "info": {"family": "rubric-contract", "variant_id": variant_id},
            }
        )
    for variant_id in sorted(frozen_repair):
        entry = frozen_repair[variant_id]
        rows.append(
            {
                "question": render_repair_prompt(entry),
                "answer": variant_id,
                "info": {"family": "rubric-repair", "variant_id": variant_id},
            }
        )
    for variant_id in sorted(frozen_referee):
        entry = frozen_referee[variant_id]
        rows.append(
            {
                "question": render_referee_prompt(entry),
                "answer": variant_id,
                "info": {"family": "referee-protocol", "variant_id": variant_id},
            }
        )
    for variant_id in sorted(frozen_redaction):
        entry = frozen_redaction[variant_id]
        variant = RedactionVariant(
            variant_id,
            entry["variant"]["title"],
            entry["variant"]["purpose"],
        )
        rows.append(
            {
                "question": render_redaction_prompt(variant),
                "answer": variant_id,
                "info": {"family": "redaction-contract", "variant_id": variant_id},
            }
        )

    if families is not None:
        unknown = set(families) - set(frozen)
        if unknown:
            raise ValueError(
                f"unknown families {sorted(unknown)}; valid: {sorted(frozen)}"
            )
        allowed = set(families)
        rows = [r for r in rows if r["info"]["family"] in allowed]

    async def terminal_state_match(completion, info, state, **_kwargs) -> float:
        module_source = parser.parse_answer(completion)
        if module_source is None:
            state["forge_outcome"] = {"skipped": "no-code"}
            return 0.0
        run_family = scoring.FAMILY_RUNNERS[info["family"]]
        outcome, score = await run_family(
            module_source, frozen[info["family"]][info["variant_id"]]
        )
        state["forge_outcome"] = outcome  # shared with the 0-weight metrics
        return score

    def parsed_code_present(completion, **_kwargs) -> float:
        return 1.0 if parser.parse_answer(completion) is not None else 0.0

    def child_completed(state, **_kwargs) -> float:
        outcome = state.get("forge_outcome") or {}
        return 1.0 if "results" in outcome else 0.0

    def structural_gate_pass(state, **_kwargs) -> float:
        outcome = state.get("forge_outcome") or {}
        gate = outcome.get("gate")
        if gate is None:
            return 1.0  # families without a structural gate
        return 1.0 if all(gate.values()) else 0.0

    def probe_error_fraction(state, **_kwargs) -> float:
        outcome = state.get("forge_outcome") or {}
        results = outcome.get("results")
        if not results:
            return 1.0
        errored = sum(1 for r in results if isinstance(r, dict) and "error" in r)
        return errored / len(results)

    rubric = vf.Rubric(
        funcs=[
            terminal_state_match,
            parsed_code_present,
            child_completed,
            structural_gate_pass,
            probe_error_fraction,
        ],
        weights=[1.0, 0.0, 0.0, 0.0, 0.0],
        parser=parser,
    )

    return vf.SingleTurnEnv(
        dataset=Dataset.from_list(rows),
        parser=parser,
        rubric=rubric,
        **kwargs,
    )
