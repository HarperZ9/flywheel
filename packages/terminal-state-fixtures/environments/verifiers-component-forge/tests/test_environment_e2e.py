"""Model-free end-to-end: the actual environment, the actual rubric path.

A synthetic "model reply" carrying the inlined reference implementation must
score reward 1.0 through the environment's own parser, reward function, child
execution, and frozen probes; a reply with no code block scores 0.0 with the
diagnostic metrics saying why. This is the slice vf-eval will exercise, minus
only the model."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import verifiers as vf
from verifiers.types import State

import verifiers_component_forge as forge

FAMILY_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "verifiers_component_forge"
    / "families"
    / "parser_contract.py"
).read_text(encoding="utf-8")


def _reference_reply(variant: dict) -> str:
    ladder = ", ".join(repr(r) for r in variant["ladder"])
    module = (
        f"{FAMILY_SOURCE}\n\n"
        f"VARIANT = Variant(({ladder},), {variant['scope']!r}, "
        f"{variant['think_strip']}, {variant['empty_hit']})\n\n"
        "class P:\n"
        "    def parse_answer(self, completion):\n"
        "        return reference_parse(VARIANT, completion)\n\n"
        "def build_parser():\n"
        "    return P()\n"
    )
    return (
        "Here is my implementation of the contract.\n\n"
        "```python\n" + module + "\n```\n\nDone."
    )


def _user_rubric(env) -> vf.Rubric:
    rubric = env.rubric
    if isinstance(rubric, vf.RubricGroup):
        rubric = rubric.rubrics[0]
    return rubric


async def _score(env, row, reply_text: str) -> State:
    state = State(
        {
            "prompt": row["question"],
            "completion": [{"role": "assistant", "content": reply_text}],
            "answer": row["answer"],
            "info": row["info"],
            "task": {},
        }
    )
    await _user_rubric(env).score_rollout(state)
    return state


def test_reference_reply_scores_one_through_the_real_environment():
    env = forge.load_environment()
    dataset = env.get_dataset()
    assert (
        len(dataset) == 337
    )  # 96 parser + 96 rubric + 77 repair + 64 referee + 4 redaction
    row = dataset[0]
    assert row["info"]["family"] == "parser-contract"
    frozen = forge._load_frozen("parser_contract.json")
    variant = frozen[row["answer"]]["variant"]

    state = asyncio.run(_score(env, row, _reference_reply(variant)))
    assert state["reward"] == 1.0, state["metrics"]
    assert state["metrics"]["parsed_code_present"] == 1.0
    assert state["metrics"]["child_completed"] == 1.0
    assert state["metrics"]["probe_error_fraction"] == 0.0


def _rubric_row(env):
    dataset = env.get_dataset()
    for i in range(len(dataset)):
        if dataset[i]["info"]["family"] == "rubric-contract":
            return dataset[i]
    raise AssertionError("no rubric-contract row")


def test_rubric_reference_scores_one_and_normalizer_trips_the_gate():
    from verifiers_component_forge.families.rubric_contract import (
        all_contracts,
        reference_module_source,
    )

    env = forge.load_environment()
    row = _rubric_row(env)
    contract = next(c for c in all_contracts() if c.variant_id == row["answer"])
    source = reference_module_source(contract)

    reply = "Implementing the contract.\n\n```python\n" + source + "\n```\n"
    state = asyncio.run(_score(env, row, reply))
    assert state["reward"] == 1.0, state["metrics"]
    assert state["metrics"]["structural_gate_pass"] == 1.0
    assert state["metrics"]["probe_error_fraction"] == 0.0

    # The classic mistake: normalize the weight vector. Same functions, same
    # names, wrong weights: the structural gate zeroes the case.
    n = len(contract.effective_weights)
    normalized = source.replace(
        "weights=[" + ", ".join(repr(w) for w in contract.effective_weights) + "]",
        "weights=[" + ", ".join(repr(w / n) for w in contract.effective_weights) + "]",
    )
    assert normalized != source
    reply2 = "```python\n" + normalized + "\n```\n"
    state2 = asyncio.run(_score(env, row, reply2))
    assert state2["reward"] == 0.0
    assert state2["metrics"]["structural_gate_pass"] == 0.0


def test_codeless_reply_scores_zero_with_diagnostics():
    env = forge.load_environment()
    row = env.get_dataset()[0]
    state = asyncio.run(_score(env, row, "I think the answer is just the tag."))
    assert state["reward"] == 0.0
    assert state["metrics"]["parsed_code_present"] == 0.0
    assert state["metrics"]["child_completed"] == 0.0


def test_redaction_reference_scores_one_and_echo_leaks_fail():
    from verifiers_component_forge.families.redaction_contract import (
        reference_module_source,
    )

    env = forge.load_environment()
    row = _redaction_row(env)

    reply = "```python\n" + reference_module_source() + "\n```\n"
    state = asyncio.run(_score(env, row, reply))
    assert state["reward"] == 1.0, state["metrics"]
    assert state["metrics"]["child_completed"] == 1.0
    assert state["metrics"]["structural_gate_pass"] == 1.0
    assert state["metrics"]["probe_error_fraction"] == 0.0

    leaky = "```python\ndef redact_record(record):\n    return record\n```\n"
    state2 = asyncio.run(_score(env, row, leaky))
    assert state2["reward"] == 0.0


def _redaction_row(env, variant_id: str = "redact-00-headers"):
    for row in env.get_dataset():
        if (
            row["info"]["family"] == "redaction-contract"
            and row["info"]["variant_id"] == variant_id
        ):
            return row
    raise AssertionError(f"no redaction-contract row for {variant_id}")


def _score_redaction_source(
    source: str, variant_id: str = "redact-00-headers"
) -> State:
    env = forge.load_environment()
    row = _redaction_row(env, variant_id)
    return asyncio.run(_score(env, row, "```python\n" + source + "\n```\n"))


def test_redaction_one_case_raw_secret_leak_zeroes_whole_variant():
    from verifiers_component_forge.families.redaction_contract import (
        reference_module_source,
    )

    source = reference_module_source().replace(
        "def redact_record(record):\n    out = _walk(record, _secret_pairs(record))",
        "def redact_record(record):\n"
        "    if record.get('case_id') == 'header-value':\n"
        "        return record\n"
        "    out = _walk(record, _secret_pairs(record))",
    )

    state = _score_redaction_source(source)

    assert state["reward"] == 0.0
    assert state["forge_outcome"]["gate"]["no_raw_secret_leaks"] is False
    assert state["metrics"]["structural_gate_pass"] == 0.0


def test_redaction_one_case_wrong_result_zeroes_whole_variant():
    from verifiers_component_forge.families.redaction_contract import (
        reference_module_source,
    )

    source = reference_module_source().replace(
        '    out["redaction_policy"] = POLICY\n    return out',
        '    out["redaction_policy"] = POLICY\n'
        "    if record.get('case_id') == 'stdout-stderr':\n"
        "        out['stdout'] = 'wrong redaction output'\n"
        "    return out",
    )

    state = _score_redaction_source(source)

    assert state["reward"] == 0.0
    assert state["forge_outcome"]["gate"]["all_exact"] is False
    assert state["metrics"]["structural_gate_pass"] == 0.0


def test_redaction_compile_error_zeroes_with_shape_gate():
    state = _score_redaction_source("def redact_record(record):\n    return {")

    assert state["reward"] == 0.0
    assert state["forge_outcome"]["gate"]["result_shape"] is False
    assert state["metrics"]["probe_error_fraction"] == 1.0
    assert state["metrics"]["structural_gate_pass"] == 0.0


def test_redaction_missing_function_zeroes_with_shape_gate():
    state = _score_redaction_source("def helper(record):\n    return record")

    assert state["reward"] == 0.0
    assert state["forge_outcome"]["gate"]["result_shape"] is False
    assert state["metrics"]["probe_error_fraction"] == 1.0
    assert state["metrics"]["structural_gate_pass"] == 0.0


def test_redaction_non_dict_return_zeroes_with_shape_gate():
    state = _score_redaction_source(
        "def redact_record(record):\n    return ['not', 'a dict']"
    )

    assert state["reward"] == 0.0
    assert state["forge_outcome"]["gate"]["result_shape"] is False
    assert state["metrics"]["probe_error_fraction"] == 1.0
    assert state["metrics"]["structural_gate_pass"] == 0.0


def test_prompt_states_the_whole_contract():
    env = forge.load_environment()
    for row in (env.get_dataset()[0], env.get_dataset()[95]):
        q = row["question"]
        assert "build_parser()" in q
        assert "EMPTY RULE" in q
        assert "Worked examples" in q
        assert "```python" in q
        # the worked-example payload never collides with scored probes
        assert "exampleAlpha" in q
