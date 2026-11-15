"""Harness smoke tests: the child-isolation slice the whole design rests on.

Pinned claims: (1) a ``python -I`` child with the parent-injected sys.path
bootstrap can import verifiers (the design's day-one de-risk); (2) the JSON
stdin/stdout protocol carries a correct module to a perfect score and a broken
module to zero without the parent crashing; (3) a hanging module is killed by
the wall clock and reported as a probe failure, not a harness error.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verifiers_component_forge.harness import runner

CORRECT_MODULE = """
class P:
    def parse_answer(self, completion):
        if isinstance(completion, str):
            text = completion
        else:
            last = completion[-1]
            content = last["content"] if isinstance(last, dict) else last.content
            if isinstance(content, list):
                content = " ".join(p["text"] for p in content if p.get("type") == "text").strip()
            text = content
        marker = "ANSWER:"
        return text.split(marker, 1)[1].strip() if marker in text else None

def build_parser():
    return P()
"""

BROKEN_MODULE = """
def build_parser():
    raise RuntimeError("boom")
"""

HANGING_MODULE = """
class P:
    def parse_answer(self, completion):
        while True:
            pass

def build_parser():
    return P()
"""

INPUTS = [
    {"kind": "text", "value": "ANSWER: 42"},
    {"kind": "chat", "messages": [{"role": "assistant", "content": "ANSWER: blue"}]},
    {
        "kind": "chat",
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "ANSWER:"},
                    {"type": "text", "text": "parts"},
                ],
            }
        ],
    },
    {"kind": "attr", "messages": [{"role": "assistant", "content": "no marker here"}]},
]
EXPECTATIONS = ["42", "blue", "parts", None]


def test_child_under_production_flags_imports_verifiers():
    """The exact production invocation (-I + injected paths) must reach
    verifiers; -I alone cannot, which is why the bootstrap exists."""
    paths = runner._verifiers_sys_paths()
    code = (
        "import sys\n"
        + "".join(f"sys.path.append({p!r})\n" for p in paths)
        + ("import verifiers\nprint(verifiers.__name__)")
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,  # the exit code is asserted below, not raised
        env=runner._scrubbed_env(),
    )
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == "verifiers"


def test_correct_module_scores_full_marks():
    result = asyncio.run(
        runner.run_child("child_driver_parser.py", CORRECT_MODULE, INPUTS)
    )
    assert result.ok, (result.failure, result.stderr_tail)
    assert runner.match_fraction(result.payload["results"], EXPECTATIONS) == 1.0


def test_broken_module_scores_zero_without_harness_error():
    result = asyncio.run(
        runner.run_child("child_driver_parser.py", BROKEN_MODULE, INPUTS)
    )
    assert result.ok, (result.failure, result.stderr_tail)
    assert runner.match_fraction(result.payload["results"], EXPECTATIONS) == 0.0


def test_hanging_module_is_wall_clock_killed():
    result = asyncio.run(
        runner.run_child(
            "child_driver_parser.py", HANGING_MODULE, INPUTS, wall_clock=5.0
        )
    )
    assert not result.ok
    assert result.failure == "timeout"


def test_oracle_values_never_reach_the_child():
    """The request document is inputs-only by construction: rebuild it the way
    run_child does and assert none of the expectation values appear."""
    request = json.dumps(
        {
            "module_source": CORRECT_MODULE,
            "inputs": INPUTS,
            "sys_paths": runner._verifiers_sys_paths(),
        }
    )
    for expectation in EXPECTATIONS:
        if expectation is None:
            continue
        # Expectations that also appear inside an INPUT are the probe's own
        # content; the check is that no expectation-only value leaks. "42",
        # "blue", "parts" all appear only inside their input text here, so
        # assert the request equals the inputs-side occurrences exactly.
        assert request.count(expectation) == json.dumps(INPUTS).count(expectation)


def test_weighted_match_fraction():
    results = ["a", "b", "c", "d"]
    expectations = ["a", "x", "c", "y"]
    # matches at positions 0 and 2, weights concentrate on 2
    assert runner.match_fraction(results, expectations, [1, 1, 7, 1]) == 0.8
