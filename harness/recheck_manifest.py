"""The ``flywheel.recheck/v1`` manifest: what a stranger needs to recheck a claim.

One JSON file per claim, in ``recheck/``. RECHECK.md documents every field;
this module loads a manifest, checks its shape, and expands placeholders.
Standard library only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA = "flywheel.recheck/v1"
LEVELS = ("integrity", "recomputation", "re-execution", "replication")
HARDWARE = ("cpu", "cpu-16gb", "gpu-8gb", "gpu-24gb", "cluster")
ACCESS = ("A0", "A1", "A2", "A3", "A4")
EXPERTISE = ("E0", "E1", "E2", "E3")
ANCHORS = ("self", "third-party", "plural")
PLACEHOLDERS = ("{python}", "{checkout}", "{repo}", "{inputs}")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

REQUIRED = ("schema", "id", "claim", "level", "repository", "commit", "command",
            "expect", "control", "needs", "access", "expertise", "anchor",
            "covers", "does_not_cover", "ci")


class ManifestError(ValueError):
    pass


def _check_expect(where: str, expect: object) -> list[str]:
    if not isinstance(expect, dict) or not isinstance(expect.get("exit_code"), int):
        return [f"{where}: needs an integer exit_code"]
    for key in ("stdout_contains", "stdout_lacks"):
        texts = expect.get(key, [])
        if not isinstance(texts, list) or not all(isinstance(s, str) for s in texts):
            return [f"{where}: {key} must be a list of strings"]
    return []


def _check_control(control: object) -> list[str]:
    if not isinstance(control, dict) or not control.get("description"):
        return ["control: needs a description; a check never shown to fail must say so"]
    problems = _check_expect("control.expect", control.get("expect"))
    mutate = control.get("mutate")
    if mutate is not None and not (isinstance(mutate, dict)
                                   and {"file", "find", "replace"} <= set(mutate)):
        problems.append("control.mutate: needs file, find and replace")
    return problems


def _check_inputs(inputs: object) -> list[str]:
    if not isinstance(inputs, list):
        return ["inputs: must be a list"]
    problems = []
    for i, row in enumerate(inputs):
        if not (isinstance(row, dict) and row.get("url", "").startswith("https://")
                and _SHA256.match(str(row.get("sha256", ""))) and row.get("save_as")):
            problems.append(f"inputs[{i}]: needs an https url, a sha256 and save_as")
    return problems


def problems_in(m: dict) -> list[str]:
    """Every shape problem in a manifest; an empty list means it is usable."""
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        return [f"missing fields: {', '.join(missing)}"]
    p: list[str] = []
    if m["schema"] != SCHEMA:
        p.append(f"schema must be {SCHEMA}")
    if not (isinstance(m["claim"], dict) and m["claim"].get("text") and m["claim"].get("where")):
        p.append("claim: needs text and where")
    if m["level"] not in LEVELS:
        p.append(f"level must be one of {LEVELS}")
    if not str(m["repository"]).startswith("https://"):
        p.append("repository must be a full https URL")
    if not _SHA.match(str(m["commit"])):
        p.append("commit must be a full 40-character SHA")
    if not (isinstance(m["command"], list) and m["command"]):
        p.append("command must be a non-empty argument list")
    setup = m.get("setup", [])
    if not (isinstance(setup, list) and all(isinstance(c, list) and c for c in setup)):
        p.append("setup must be a list of argument lists")
    p += _check_expect("expect", m["expect"]) + _check_control(m["control"])
    p += _check_inputs(m.get("inputs", []))
    needs = m["needs"] if isinstance(m["needs"], dict) else {}
    if needs.get("hardware") not in HARDWARE:
        p.append(f"needs.hardware must be one of {HARDWARE}")
    if not isinstance(needs.get("seconds"), (int, float)):
        p.append("needs.seconds: the expected compute time")
    for key, allowed in (("access", ACCESS), ("expertise", EXPERTISE), ("anchor", ANCHORS)):
        if m[key] not in allowed:
            p.append(f"{key} must be one of {allowed}")
    if m["ci"] is not True and not m.get("ci_skip_reason"):
        p.append("ci: false needs ci_skip_reason")
    return p


def load(path: Path) -> dict:
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = problems_in(m)
    if problems:
        raise ManifestError(f"{path}: " + "; ".join(problems))
    return m


def discover(root: Path) -> list[Path]:
    return sorted((Path(root) / "recheck").glob("*.json"))


def expand(value: str, places: dict[str, str]) -> str:
    for key, sub in places.items():
        value = value.replace("{" + key + "}", sub)
    return value
