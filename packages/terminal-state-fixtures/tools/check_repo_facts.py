"""Bind the drawn card to the code, the frozen data and the recorded runs.

The artwork gate settles whether a card fits its columns and matches its spec.
It cannot settle whether the card is true. This reads the scorer, the frozen
case files, the test files and the recorded evaluation runs, rebuilds every
number the card draws, and fails when a drawn number and its source disagree.

Standard library only, so it runs on any machine with Python and without the
verifiers or datasets packages the environments themselves need.
"""

from __future__ import annotations

import ast
import io
import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "art" / "terminal-state-fixtures.art.json"

MLFLOW = "environments/mlflow_terminal_state"
FORGE = "environments/verifiers-component-forge"
METR = "environments/metr_terminal_state_runs"
SCORER = f"{MLFLOW}/mlflow_terminal_state.py"
SCORING = f"{FORGE}/verifiers_component_forge/scoring.py"
DATA = f"{FORGE}/verifiers_component_forge/data"

EXPECTATION_KEY = {
    "parser_contract": "probes",
    "redaction_contract": "fixtures",
    "referee_protocol": "scripts",
    "rubric_contract": "fixtures",
    "rubric_repair": "fixtures",
}

WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
    7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
    12: "twelve", 13: "thirteen", 14: "fourteen",
}


def _read(relative: str) -> str:
    return io.open(ROOT / relative, encoding="utf-8").read()


def _spec_fields() -> dict[str, str]:
    spec = json.loads(_read(SPEC.relative_to(ROOT).as_posix()))
    card = spec["cards"][0]
    return {row["key"]: row["value"] for row in card["fields"]}


def _scorer():
    """Load Verdict, RunRecord, score and FIELDS out of the environment module.

    The module imports verifiers and datasets at the top, which are not
    installed on a plain runner, so the definitions this gate needs are
    lifted out of the parse tree and executed on their own. It is the
    repository's real scorer running, not a copy of it.
    """
    tree = ast.parse(_read(SCORER))
    kept = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            if all(a.name not in ("verifiers", "datasets") for a in node.names):
                kept.append(node)
        elif isinstance(node, ast.ImportFrom):
            if node.module not in ("verifiers", "datasets"):
                kept.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in ("Verdict", "RunRecord"):
            kept.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "score":
            kept.append(node)
        elif isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "FIELDS":
            kept.append(node)
    namespace: dict = {}
    exec(compile(ast.Module(body=kept, type_ignores=[]), SCORER, "exec"), namespace)
    for name in ("Verdict", "RunRecord", "score", "FIELDS"):
        assert name in namespace, f"{SCORER} no longer defines {name}"
    return namespace


def _records(namespace) -> list[tuple[object, bool, dict]]:
    fields, record, score = namespace["FIELDS"], namespace["RunRecord"], namespace["score"]
    rows = []
    for combination in itertools.product(*fields.values()):
        values = dict(zip(fields, combination))
        verdict, counts = score(record(**values))
        rows.append((verdict, counts, values))
    return rows


def _verdicts(namespace) -> list[str]:
    return [member.value for member in namespace["Verdict"]]


def _cases() -> dict[str, dict]:
    return {
        path.stem: json.loads(io.open(path, encoding="utf-8").read())
        for path in sorted((ROOT / DATA).glob("*.json"))
    }


def _expectations(cases: dict[str, dict]) -> dict[str, int]:
    return {
        family: sum(len(case[EXPECTATION_KEY[family]]) for case in entries.values())
        for family, entries in cases.items()
    }


def _test_functions() -> int:
    total = 0
    for path in sorted(ROOT.glob("environments/*/tests/test_*.py")):
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return total


def _eval_runs(environment: str) -> list[Path]:
    return sorted((ROOT / environment).glob("outputs/evals/*/*/metadata.json"))


def _rollouts(runs: list[Path]) -> int:
    return sum(
        sum(1 for line in io.open(run.with_name("results.jsonl"), encoding="utf-8") if line.strip())
        for run in runs
    )


def _family_runners() -> set[str]:
    text = _read(SCORING)
    block = text[text.index("FAMILY_RUNNERS = {"):]
    return set(re.findall(r'"([\w-]+)":', block[: block.index("}")]))


def measure() -> dict[str, str]:
    namespace = _scorer()
    rows = _records(namespace)
    cases = _cases()
    expectations = _expectations(cases)
    counted = sum(1 for _, counts, _ in rows if counts)
    forge_runs = _eval_runs(FORGE)
    mlflow_runs = _eval_runs(MLFLOW)
    environments = sum(1 for path in (ROOT / "environments").iterdir() if path.is_dir())
    return {
        "environments": f"{WORDS[environments]} of them",
        "record fields": f"{WORDS[len(namespace['FIELDS'])]} of them",
        "dataset records": f"{len(rows)} rows",
        "terminal verdicts": f"{WORDS[len(_verdicts(namespace))]} of them",
        "in the denominator": f"{counted} of {len(rows)}",
        "forge families": f"{WORDS[len(cases)]} of them",
        "forge cases": f"{sum(len(entries) for entries in cases.values())} in all",
        "frozen expectations": f"{sum(expectations.values()):,} pinned",
        "referee scripts": f"{expectations['referee_protocol']} replayed",
        "repair cases": f"{len(cases['rubric_repair'])} of them",
        "pinned tests": f"{_test_functions()} declared",
        "recorded eval runs": f"{WORDS[len(forge_runs)]} of them",
        "recorded rollouts": f"{_rollouts(forge_runs)} in all",
        "scored runs on mlflow": (
            "none in the tree" if not mlflow_runs else f"{len(mlflow_runs)} of them"
        ),
    }


def check_card_rows_match_the_source() -> None:
    drawn = _spec_fields()
    for key, value in measure().items():
        assert key in drawn, f"the card no longer draws a row for {key}"
        assert drawn[key] == value, (
            f"{key}: the card says {drawn[key]!r}, the source says {value!r}"
        )


def check_exclusions_are_settled_before_the_oracle() -> None:
    """The drawing's central claim, checked against the scorer's own behaviour.

    A record that did not return, or whose provider refused or produced
    unparseable output, must leave the denominator whatever the oracle says.
    A returned record whose receipt or artifact does not match must be refuted
    even when the oracle passed, because integrity outranks the oracle.
    """
    namespace = _scorer()
    verdict_type = namespace["Verdict"]
    excluded = 0
    integrity = 0
    for verdict, counts, values in _records(namespace):
        not_a_run = values["execution"] != "returned" or values["provider"] != "ok"
        if not_a_run:
            assert not counts, f"{values} left the exclusion path and entered the denominator"
            excluded += 1
            continue
        if values["receipt"] == "mismatch" or values["artifact"] == "mismatch":
            assert verdict == verdict_type.REFUTED, f"{values} was not refuted by integrity"
            assert counts, f"{values} was refuted but left the denominator"
            integrity += 1
    assert excluded, "no record reached the exclusion path, so the check proves nothing"
    assert integrity, "no record reached the integrity path, so the check proves nothing"


def check_the_families_are_declared_twice() -> None:
    """Frozen data and the scoring table each name the families, separately."""
    from_data = {family.replace("_", "-") for family in _cases()}
    from_code = _family_runners()
    assert from_data == from_code, (
        f"only in the data files: {sorted(from_data - from_code)}; "
        f"only in the scoring table: {sorted(from_code - from_data)}"
    )


def check_every_frozen_case_carries_its_expectations() -> None:
    """A case with an empty expectation list would score anything at all."""
    for family, entries in _cases().items():
        key = EXPECTATION_KEY[family]
        assert entries, f"{family}.json holds no cases"
        for name, case in entries.items():
            assert key in case, f"{family}/{name} has no {key} to be scored against"
            assert case[key], f"{family}/{name} carries an empty {key} list"


def check_the_marked_row_is_still_an_honest_null() -> None:
    """The card says no model score is recorded for the first environment."""
    assert not _eval_runs(MLFLOW), (
        "a recorded evaluation now exists for the record-scoring environment, "
        "so the marked row is stale and the card should draw the count"
    )
    assert not (ROOT / MLFLOW / "outputs").exists(), (
        f"{MLFLOW}/outputs now exists; check whether a run was recorded"
    )
    assert _eval_runs(FORGE), "the recorded runs the card counts have gone missing"


def check_the_task_family_agrees_with_the_scorer() -> None:
    """Two environments classify the same records, so they must not drift apart.

    The METR task family carries its own copy of the eight rules. It is
    standard library only, so it is executed whole and compared with the
    reference scorer on every record of the full product, both ways round.
    """
    namespace = _scorer()
    family: dict = {}
    exec(compile(_read(f"{METR}/{Path(METR).name}.py"), METR, "exec"), family)
    task_family = family["TaskFamily"]
    assert {k: tuple(v) for k, v in namespace["FIELDS"].items()} == task_family.values, (
        "the two environments no longer enumerate the same fields and values"
    )
    tasks = task_family.get_tasks()
    rows = _records(namespace)
    assert len(tasks) == len(rows), f"{len(tasks)} tasks against {len(rows)} dataset rows"
    seen = set()
    for verdict, counts, values in rows:
        theirs = task_family.classify(values)
        assert theirs == (verdict.value, counts), (
            f"{values}: the scorer says {(verdict.value, counts)}, the task family says {theirs}"
        )
        seen.add(tuple(values[field] for field in task_family.fields))
    stored = {tuple(task[field] for field in task_family.fields) for task in tasks.values()}
    assert stored == seen, "the task family and the dataset hold different records"


CHECKS = [
    check_card_rows_match_the_source,
    check_exclusions_are_settled_before_the_oracle,
    check_the_families_are_declared_twice,
    check_every_frozen_case_carries_its_expectations,
    check_the_marked_row_is_still_an_honest_null,
    check_the_task_family_agrees_with_the_scorer,
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
