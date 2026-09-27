"""Judge the installed-app acceptance: each check, each lane, the run.

A check result is ``pass``, ``fail``, ``not_measurable`` (a host fact hides
the state, for example a model server the build machine runs) or absent (the
check never ran, which counts as a failure). A lane is ``AT_CLASS`` only when
no check failed or went missing; a held lane is ``HELD``; anything else is
``BELOW_BAR`` with the failed checks as its reason. The run is ``PASS`` only
when every lane is ``AT_CLASS`` and every run-level guard held.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

_LOCAL_ONLY = (
    "A throwaway profile on the build machine with a System32-only PATH, not a "
    "consumer Windows 11 install or a clean VM; host DLLs, the network and any "
    "model server the host runs were reachable.",
    "The acceptance installer differs from the release installer in its AppId, "
    "Start menu group and output name only, so it cannot touch the Flywheel "
    "already installed here.",
)
_CI_ONLY = (
    "A throwaway profile on a GitHub-hosted Windows Server runner, run as an "
    "administrator with a System32-only PATH: not a consumer Windows 11 install, "
    "and not a standard user's read-only Program Files. The network was reachable.",
)
_COMMON = (
    "No provider-backed success: no real provider key was used; key-backed tools "
    "stay 'after setup: untested'.",
    "No model quality: the stub model server answers one fixed word; a model-lane "
    "pass shows the lane reached a model server and the engine's guards held.",
    "No bulletin write and no actuation; a board read contacts the public board.",
    "One fixture assertion per main tool; not result correctness in general.",
    "The desktop UI was not driven: the checks call the engine routes the app calls.",
)
DOES_NOT_PROVE = _LOCAL_ONLY + _COMMON


def does_not_prove(environ: Mapping[str, str]) -> list[str]:
    """What this run does not prove, for where it ran: a GitHub Actions runner
    builds and accepts the release installer itself."""
    ci = environ.get("GITHUB_ACTIONS", "").lower() == "true"
    return list((_CI_ONLY if ci else _LOCAL_ONLY) + _COMMON)


@dataclass(frozen=True)
class Outcome:
    result: str                      # pass | fail | not_measurable
    evidence: dict = field(default_factory=dict)


def evaluate_state(check, row: dict | None, *, host: dict) -> Outcome:
    if not isinstance(row, dict):
        return Outcome("fail", {"state": None, "reason": "lane_missing_from_roster"})
    evidence = {"state": row.get("state"), "code": row.get("code")}
    ok = row.get("state") in check.states and (not check.code or row.get("code") == check.code)
    if ok:
        return Outcome("pass", evidence)
    if check.confound and host.get(check.confound):
        return Outcome("not_measurable", {**evidence, "host": check.confound})
    return Outcome("fail", {**evidence, "expected": list(check.states)})


def _code(body: object) -> object:
    return body.get("code") if isinstance(body, dict) else None


def evaluate_call(check, status: int, body: object, *, stub_delta: int | None = None) -> Outcome:
    """A 200 check needs its assertion; a 403 (``DENIED``) check needs the
    governance gate's own refusal; any other refusal check needs its code, so a
    dead engine or a misspelled tool never passes as a refusal."""
    evidence = {"status": status, "code": _code(body)}
    if stub_delta is not None:
        evidence["stub_generate_requests"] = stub_delta
    if check.expect_status == 200:
        ok = status == 200 and (check.assert_ is None or bool(_safe(check.assert_, body)))
        if ok and check.stub_hit:
            ok = bool(stub_delta)
    elif check.expect_status == 403:
        denied = isinstance(body, dict) and body.get("governance_denied") is True
        evidence["governance_denied"] = denied
        ok = status == 403 and denied
    else:
        ok = status != 200 and bool(check.expect_code) and _code(body) == check.expect_code
    return Outcome("pass" if ok else "fail", evidence)


def _safe(assertion, body: object) -> bool:
    try:
        return assertion(body)
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def evaluate_tools(lane: str, status: int, body: object) -> Outcome:
    from harness.lane_tool_policy import main_tools
    listed = body.get("tools") if isinstance(body, dict) else None
    if status != 200 or not isinstance(listed, list):
        return Outcome("fail", {"status": status, "code": _code(body)})
    by_name = {t.get("name"): t for t in listed if isinstance(t, dict)}
    ready = sorted(n for n in main_tools(lane) if by_name.get(n, {}).get("main")
                   and isinstance(by_name[n].get("inputSchema"), dict)
                   and (by_name[n].get("admitted") or by_name[n].get("tier") == "T2"))
    evidence = {"status": status, "tools": len(listed),
                "admitted": sum(1 for t in by_name.values() if t.get("admitted")),
                "main_with_schema": ready}
    return Outcome("pass" if set(ready) == set(main_tools(lane)) else "fail", evidence)


def evaluate_home_path(check, home: Path) -> Outcome:
    folder = Path(home).joinpath(*check.path)
    files = [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []
    return Outcome("pass" if files else "fail",
                   {"folder": "/".join(check.path), "files": len(files)})


def lane_verdict(case, outcomes: dict) -> dict:
    failed, unmeasured = [], []
    for check in case.checks:
        outcome = outcomes.get(check.name)
        if outcome is None:
            failed.append({"check": check.name, "reason": "not_run"})
        elif outcome.result == "not_measurable":
            unmeasured.append(check.name)
        elif outcome.result != "pass":
            failed.append({"check": check.name, **outcome.evidence})
    held = case.class_expected == "held"
    verdict = "HELD" if held else ("BELOW_BAR" if failed else "AT_CLASS")
    return {"class_plan": case.class_plan, "class_expected": case.class_expected,
            "basis": case.basis,
            "class_measured": case.class_expected if verdict == "AT_CLASS" else None,
            "verdict": verdict, "failed": failed, "not_measurable": unmeasured,
            "untested": list(case.untested),
            "checks": {name: {"result": o.result, **o.evidence}
                       for name, o in outcomes.items()}}


def summary(rows: dict, guards: dict | None = None) -> dict:
    below = sorted(lane for lane, row in rows.items() if row["verdict"] != "AT_CLASS")
    by_class: dict[str, int] = {}
    for row in rows.values():
        if row.get("class_measured"):
            by_class[row["class_measured"]] = by_class.get(row["class_measured"], 0) + 1
    broken = sorted(name for name, ok in (guards or {}).items() if not ok)
    verdict = "FAIL" if broken else ("BELOW_BAR" if below else "PASS")
    return {"verdict": verdict, "below_bar": below, "by_class": by_class,
            "guards_failed": broken}


def redact(value: object, secrets: tuple[str, ...]) -> tuple[object, int]:
    """``value`` with every secret replaced, and how many were found."""
    if any(not s for s in secrets):
        raise ValueError("an empty secret cannot be redacted")
    hits = 0

    def walk(item: object) -> object:
        nonlocal hits
        if isinstance(item, str):
            for secret in secrets:
                if secret in item:
                    hits += item.count(secret)
                    item = item.replace(secret, "<redacted>")
            return item
        if isinstance(item, dict):
            return {walk(k): walk(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [walk(v) for v in item]
        return item
    return walk(value), hits
