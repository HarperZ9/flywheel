"""Oracle soundness for the parser-contract family.

Three layers of protection, so a reference bug cannot freeze into "truth":
hand-derived semantic rows written independently of grammar and generator;
structural invariants over the frozen file (regeneration is byte-identical,
weights sum to one, every variant carries edge cells); and the discrimination
floor, run END-TO-END through the child driver: a module wrapping the
reference scores 1.0 on the frozen probes while the stock ``vf.XMLParser``
falls measurably short on the trap cells it was never built to honor.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verifiers_component_forge.families import parser_contract as pc
from verifiers_component_forge.families import (
    parser_contract_grammar as pcg,
)
from verifiers_component_forge.harness import runner

DATA = (
    Path(__file__).resolve().parents[1]
    / "verifiers_component_forge"
    / "data"
    / "parser_contract.json"
)


# ---- hand-derived semantics (no grammar, no generator) ----------------------

V = pc.Variant


def test_tag_last_pair_wins_and_strips():
    v = V(("tag:answer",), "last", False, False)
    text = "<answer>old</answer> mid <answer>  new  </answer> tail"
    assert pc.reference_parse(v, text) == "new"


def test_empty_semantics_flip_on_empty_hit():
    text = "before <answer></answer> after"
    assert pc.reference_parse(V(("tag:answer",), "last", False, False), text) is None
    assert pc.reference_parse(V(("tag:answer",), "last", False, True), text) == ""


def test_missing_close_tag_is_a_miss_not_empty():
    v = V(("tag:answer", "lastline"), "last", False, True)
    assert pc.reference_parse(v, "x\n<answer>abandoned\nfinal line") == "final line"


def test_think_strip_requires_both_tags():
    stripped = V(("tag:answer",), "last", True, False)
    unstripped = V(("tag:answer",), "last", False, False)
    both = "<think><answer>hidden</answer></think> outside"
    assert pc.reference_parse(stripped, both) is None
    assert pc.reference_parse(unstripped, both) == "hidden"
    lone = "<think> no close tag <answer>visible</answer>"
    assert pc.reference_parse(stripped, lone) == "visible"


def test_scope_last_vs_joined_on_cross_message_hit():
    chat = [
        {"role": "assistant", "content": "<answer>early</answer>"},
        {"role": "assistant", "content": "no tags here"},
    ]
    assert pc.reference_parse(V(("tag:answer",), "last", False, False), chat) is None
    assert (
        pc.reference_parse(V(("tag:answer",), "joined", False, False), chat) == "early"
    )


def test_precedence_beats_document_order():
    v = V(("tag:answer", "fence:python"), "last", False, False)
    text = "```python\nfenced\n```\n<answer>tagged</answer>"
    assert pc.reference_parse(v, text) == "tagged"


def test_multipart_join_breaks_split_tags():
    v = V(("tag:answer",), "last", False, False)
    split = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "<answ"},
                {"type": "text", "text": "er>payload</answer>"},
            ],
        }
    ]
    joined = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "<answer>pay"},
                {"type": "text", "text": "load</answer>"},
            ],
        }
    ]
    assert pc.reference_parse(v, split) is None  # "<answ er>" is no tag
    assert pc.reference_parse(v, joined) == "pay load"  # single-space join


def test_prefix_takes_last_marker_line_then_applies_empty_rule():
    """Occurrence selection happens FIRST (last marker line), THEN the empty
    rule applies to what was selected. A bare final marker line therefore
    yields "" under empty_hit, and a rung MISS (never a fall-back to an
    earlier marker line) without it. This row exists because the opposite
    reading is plausible; the contract pins this one."""
    v = V(("prefix:ANSWER:",), "last", False, True)
    text = "ANSWER: one\nnoise\n  ANSWER: two  \nANSWER:\n"
    assert pc.reference_parse(v, text) == ""  # last marker line is bare, empty hits
    assert (
        pc.reference_parse(V(("prefix:ANSWER:",), "last", False, False), text) is None
    )


def test_whitespace_only_scope_misses_everything():
    v = V(("tag:answer", "lastline"), "last", False, True)
    assert pc.reference_parse(v, "   \n\t  \n") is None


# ---- frozen-file invariants -------------------------------------------------


def _frozen() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_frozen_file_matches_regeneration():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generation"))
    import generate

    regenerated = generate._dumps(generate.build_parser_contract())
    assert regenerated == DATA.read_text(encoding="utf-8")


def test_every_variant_weights_sum_to_one_with_edge_credit():
    data = _frozen()
    assert len(data) == 96
    for vid, entry in data.items():
        weights = [p["weight"] for p in entry["probes"]]
        assert abs(sum(weights) - 1.0) < 1e-9, vid
        edge = sum(p["weight"] for p in entry["probes"] if p["cell"] in pcg.EDGE_CELLS)
        assert abs(edge - pcg.EDGE_CREDIT) < 1e-9, (vid, edge)
        # Depth-1 prefix ladders bottom out at 13 probes (no unclosed
        # form, no split-tag cell); everything else carries more.
        assert len(entry["probes"]) >= 13, vid


def test_misses_exist_but_do_not_dominate():
    data = _frozen()
    n = sum(len(e["probes"]) for e in data.values())
    n_none = sum(1 for e in data.values() for p in e["probes"] if p["expect"] is None)
    assert 0.05 < n_none / n < 0.5


# ---- discrimination floor, end to end through the child ---------------------

TRAP_VARIANT = "pc-00-last-think0-empty0"

REFERENCE_MODULE_TEMPLATE = """
{family_source}

VARIANT = Variant(({ladder},), {scope!r}, {think_strip}, {empty_hit})

class P:
    def parse_answer(self, completion):
        return reference_parse(VARIANT, completion)

def build_parser():
    return P()
"""

STOCK_XMLPARSER_MODULE = """
import verifiers as vf

def build_parser():
    return vf.XMLParser(["answer"])
"""


def _score_module(module_source: str, entry: dict) -> float:
    inputs = [p["recipe"] for p in entry["probes"]]
    result = asyncio.run(
        runner.run_child(
            "child_driver_parser.py", module_source, inputs, wall_clock=120.0
        )
    )
    assert result.ok, (result.failure, result.stderr_tail)
    return runner.match_fraction(
        result.payload["results"],
        [p["expect"] for p in entry["probes"]],
        [p["weight"] for p in entry["probes"]],
    )


def test_reference_scores_full_marks_and_stock_parser_does_not():
    entry = _frozen()[TRAP_VARIANT]
    family_source = (
        Path(__file__).resolve().parents[1]
        / "verifiers_component_forge"
        / "families"
        / "parser_contract.py"
    ).read_text(encoding="utf-8")
    # The family module uses only stdlib; inline it so the child needs no
    # package imports, mirroring how a contract-faithful agent would work.
    v = entry["variant"]
    reference_module = REFERENCE_MODULE_TEMPLATE.format(
        family_source=family_source,
        ladder=", ".join(repr(r) for r in v["ladder"]),
        scope=v["scope"],
        think_strip=v["think_strip"],
        empty_hit=v["empty_hit"],
    )
    assert _score_module(reference_module, entry) == 1.0

    # The discrimination ladder, pinned with margin below measured values
    # (0.867 / 0.65 / 0.25 at freeze time): the stock parser scores well on
    # the shallowest contract and collapses as ladder depth and scope rules
    # engage, which is the family's difficulty axis working as designed.
    frozen = _frozen()
    for vid, ceiling in (
        (TRAP_VARIANT, 0.95),
        ("pc-06-last-think1-empty1", 0.80),
        ("pc-11-joined-think1-empty1", 0.45),
    ):
        stock = _score_module(STOCK_XMLPARSER_MODULE, frozen[vid])
        assert stock < ceiling, (
            f"stock XMLParser scored {stock} on {vid}; traps have decayed"
        )
