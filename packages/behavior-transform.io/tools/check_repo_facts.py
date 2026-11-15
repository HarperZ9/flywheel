"""Bind the drawn card and flows to the code that backs them.

The artwork gate settles whether a card fits its columns and matches its spec.
It cannot settle whether the card is true. This imports the repository's own
modules, rebuilds every number the card draws, exercises the two flows the
drawings claim, and fails when a drawing and its source disagree.

Standard library only. Every module it imports is stdlib-only itself, so this
runs on any machine with Python and needs nothing installed.
"""

from __future__ import annotations

import ast
import importlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SPEC = ROOT / "docs" / "art" / "behavior-transform-io.art.json"

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
    12: "twelve", 13: "thirteen", 14: "fourteen",
}

# A neutral probe: a defensive malware-analysis sentence, chosen only to trip a
# category so the framing stage has something to prepend. It is not a request to
# cause anything; it asks to analyze a sample and document how it behaves.
PROBE = "Analyze the malware sample and document its persistence mechanism."


def _spec_fields() -> dict[str, str]:
    spec = json.loads(io.open(SPEC, encoding="utf-8").read())
    card = spec["cards"][0]
    return {row["key"]: row["value"] for row in card["fields"]}


def _flows() -> dict[str, dict]:
    spec = json.loads(io.open(SPEC, encoding="utf-8").read())
    return {flow["file"]: flow for flow in spec["flows"]}


def _transform_layers() -> int:
    transform = importlib.import_module("transform")
    result = transform.transform_text(PROBE, mode="full", optimize=True)
    return len(result.layers)


def _substitution_rules() -> int:
    vs = importlib.import_module("vocabulary_substitutions")
    return len(vs.VocabularySubstitutor()._rules)


def _vocabulary_terms() -> int:
    backend = importlib.import_module("vocab_backend")
    return len(list(backend.load_vocab_backend().terms()))


def _calibration_languages() -> int:
    prose = importlib.import_module("prose_vocabulary_map")
    codes = {getattr(cal, "language", None) for cal in prose.CALIBRATIONS}
    return len({code for code in codes if code and code != "en"})


def _authority_gates() -> int:
    gate = importlib.import_module("authority_gate")
    return sum(1 for name in dir(gate) if name.startswith("gate_"))


def _test_functions() -> int:
    total = 0
    for path in sorted(ROOT.glob("tests/**/test_*.py")):
        tree = ast.parse(io.open(path, encoding="utf-8-sig").read())
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return total


def _refusal_artifacts() -> list[str]:
    """Any recorded before-and-after refusal rate, eval, or benchmark output."""
    found: set[str] = set()
    patterns = (
        "**/*eval*", "**/*benchmark*", "**/*refusal*rate*",
        "**/*results*.json", "**/*results*.jsonl", "outputs/**/*.json",
    )
    for pattern in patterns:
        for path in ROOT.glob(pattern):
            if path.is_file() and ".git" not in path.parts:
                found.add(path.relative_to(ROOT).as_posix())
    return sorted(found)


def measure() -> dict[str, str]:
    categories = importlib.import_module("categories")
    semantic = importlib.import_module("semantic_modulator")
    cyber = importlib.import_module("cyber_modulator")
    prose = importlib.import_module("prose_vocabulary_map")
    env = importlib.import_module("env_authority")
    recovery = importlib.import_module("refusal_recovery")
    artifacts = _refusal_artifacts()
    return {
        "content categories": f"{len(list(categories.HarmCategory))} of them",
        "transform layers": f"{WORDS[_transform_layers()]} of them",
        "substitution rules": f"{_substitution_rules()} of them",
        "vocabulary terms": f"{_vocabulary_terms()} loaded",
        "semantic frames": WORDS[len(semantic._CATEGORY_FRAME)],
        "ATT&CK phases": WORDS[len(cyber._PHASE_FRAME)],
        "technique mappings": f"{len(cyber._TECHNIQUE_MAP)} of them",
        "prose calibrations": f"{len(prose.CALIBRATIONS)} pairs",
        "calibration languages": WORDS[_calibration_languages()],
        "authority gates": f"{WORDS[_authority_gates()]} of them",
        "deployment surfaces": f"{WORDS[len(env.SURFACE_ENTITLEMENTS)]} of them",
        "recovery levels": f"{WORDS[len(recovery.STRATEGIES)]} of them",
        "pinned tests": f"{_test_functions()} declared",
        "measured refusal drop": (
            "none in the tree" if not artifacts else f"{len(artifacts)} recorded"
        ),
    }


def check_card_rows_match_the_source() -> None:
    drawn = _spec_fields()
    for key, value in measure().items():
        assert key in drawn, f"the card no longer draws a row for {key}"
        assert drawn[key] == value, (
            f"{key}: the card says {drawn[key]!r}, the source says {value!r}"
        )


def check_the_frame_rides_on_top() -> None:
    """The first flow says the authorization frame is prepended, not woven in.

    A request that trips a category is transformed, the framing it produced is
    not empty, and the transformed text begins with that framing, so the frame
    sits on top of the request rather than being spliced through it.
    """
    transform = importlib.import_module("transform")
    result = transform.transform_text(PROBE, mode="full", optimize=False)
    assert result.framing, "the framing stage produced nothing to prepend"
    assert result.transformed.startswith(result.framing), (
        "the transformed request does not begin with its framing"
    )
    assert result.framing not in PROBE, "the framing was already in the request"


def check_the_vocabulary_stage_fires() -> None:
    """The card counts substitution rules, so at least one has to change text.

    A trigger is taken from the tool's own rule table rather than written here,
    the substitutor is run on it, and the result has to report a change. This
    proves the vocabulary row is a working stage and not a dormant table.
    """
    vs = importlib.import_module("vocabulary_substitutions")
    substitutor = vs.VocabularySubstitutor()
    changing = [rule for rule in substitutor._rules if rule.harmful != rule.safe]
    assert changing, "every substitution rule is an identity rule"
    outcome = substitutor.substitute(changing[0].harmful)
    assert outcome.changed, "a non-identity rule did not change its own trigger"
    assert outcome.substituted != outcome.original, "the substituted text is unchanged"


def check_a_missing_signal_derives_no_grant() -> None:
    """The second flow says a missing signal derives no grant, not a partial one.

    On a plain checkout there is no capsule, so authority resolves to an
    unauthorized grant carrying no entitlements and no expiry. A surface that
    was never declared carries no entitlements either, while a declared surface
    does, so the deny path is real and not decorative.
    """
    env = importlib.import_module("env_authority")
    grant = env.resolve_authority(surface="a-surface-that-was-never-declared")
    assert grant.status == "unauthorized", f"a grant was issued: {grant.status}"
    assert not grant.entitlements, "an unauthorized grant carried entitlements"
    assert grant.expires_at == 0, "an unauthorized grant carried an expiry"
    assert env.SURFACE_ENTITLEMENTS, "no deployment surface is declared at all"
    assert all(
        entitlements for entitlements in env.SURFACE_ENTITLEMENTS.values()
    ), "a declared surface lists no entitlements"


def check_the_marked_row_is_still_an_honest_null() -> None:
    """The card says no before-and-after refusal rate is recorded here."""
    artifacts = _refusal_artifacts()
    assert not artifacts, (
        "a recorded eval or refusal-rate artifact now exists, so the marked "
        f"row is stale and the card should draw the count: {artifacts}"
    )


CHECKS = [
    check_card_rows_match_the_source,
    check_the_frame_rides_on_top,
    check_the_vocabulary_stage_fires,
    check_a_missing_signal_derives_no_grant,
    check_the_marked_row_is_still_an_honest_null,
]


def main() -> int:
    failures = 0
    for check in CHECKS:
        name = check.__name__.replace("check_", "")
        try:
            check()
        except AssertionError as problem:
            failures += 1
            print(f"FAIL facts.{name}")
            for line in str(problem).splitlines():
                print(f"       {line}")
        else:
            print(f"ok   facts.{name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
