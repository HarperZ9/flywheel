"""senses.py: tools an agent can point at an item, routed by input kind.

The catalogue is one tab-separated file, `sense_data/SENSES.tsv`: one row per tool
with its input kinds, exact call, verified status and cost, plus machine
columns (`id`, `run`, `match_ext`, `network`, `budget_s`, `budget_mb`,
`writes`). `generate` turns each row an agent can call today into a manifest
(`sense_data/manifests/<id>.interop.json`) carrying a `sense` block; `check`
regenerates in memory and reports every file that differs, so the table and the
manifests cannot drift apart unnoticed. `match` returns every sense manifest
whose kinds meet an item's kinds; it never picks one.
"""
from __future__ import annotations

import csv
import io
import json
import os

from .kinds import KINDS
from .manifest import Manifest

SCHEMA = "plexus.sense/1"
HERE = os.path.dirname(os.path.abspath(__file__))
SENSES_DIR = os.path.join(HERE, "sense_data")
TSV = os.path.join(SENSES_DIR, "SENSES.tsv")
MANIFEST_DIR = os.path.join(SENSES_DIR, "manifests")
CATALOGUE_COLUMNS = ["family", "tool", "home", "input_kinds", "returns", "angle",
                     "agent_entry", "exact_call", "verified", "cost"]
MACHINE_COLUMNS = ["id", "run", "match_ext", "network", "budget_s", "budget_mb", "writes"]


class SensesError(ValueError):
    """The catalogue breaks a rule the router depends on."""


def read_rows(text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(text), delimiter="\t"))
    if not rows:
        raise SensesError("SENSES.tsv has no rows")
    want = CATALOGUE_COLUMNS + MACHINE_COLUMNS
    have = list(rows[0].keys())
    if have != want:
        raise SensesError(f"SENSES.tsv columns {have} != {want}")
    return rows


def callable_today(row: dict) -> bool:
    """An agent can reach it from a command line or an MCP call (or a run is declared)."""
    entry = row["agent_entry"].lower()
    return bool(row["run"]) or "command line" in entry or (
        "mcp" in entry and "not registered" not in entry)


def _kinds(row: dict) -> list[str]:
    kinds = [k.strip() for k in row["input_kinds"].split(";") if k.strip()]
    bad = [k for k in kinds if k not in KINDS]
    if bad or not kinds:
        raise SensesError(f"{row['id']}: input kinds {bad or kinds} not in the vocabulary")
    return kinds


def row_to_manifest(row: dict) -> dict:
    run = json.loads(row["run"]) if row["run"] else None
    if run is not None and not ({"cli", "mcp"} & set(run)):
        raise SensesError(f"{row['id']}: run needs a cli or an mcp block")
    sense = {
        "schema": SCHEMA, "tool": row["tool"], "family": row["family"], "home": row["home"],
        "accepts": _kinds(row), "returns": row["returns"], "angle": row["angle"],
        "agent_entry": row["agent_entry"], "exact_call": row["exact_call"],
        "verified": row["verified"], "cost": row["cost"], "run": run,
        "match_ext": row["match_ext"].split(), "network": row["network"] == "1",
        "budget": {"time_s": float(row["budget_s"] or 0), "memory_mb": int(row["budget_mb"] or 0)},
        "writes": row["writes"].split(),
    }
    return {"organ": row["id"], "invoke": {"exact_call": row["exact_call"]},
            "emits": [], "consumes": [], "evidence": [row["home"]], "sense": sense}


def _dump(d: dict) -> str:
    return json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def generate(tsv_text: str) -> dict[str, str]:
    """{file name: content} for every row an agent can call today."""
    out, ids = {}, set()
    for row in read_rows(tsv_text):
        if row["id"] in ids:
            raise SensesError(f"duplicate id {row['id']}")
        ids.add(row["id"])
        if callable_today(row):
            out[f"{row['id']}.interop.json"] = _dump(row_to_manifest(row))
    return out


def check(tsv_path: str = TSV, manifest_dir: str = MANIFEST_DIR) -> list[str]:
    """Differences between the table and the manifests on disk (empty = in step)."""
    with open(tsv_path, encoding="utf-8") as f:
        want = generate(f.read())
    have = {n for n in os.listdir(manifest_dir) if n.endswith(".interop.json")} \
        if os.path.isdir(manifest_dir) else set()
    problems = [f"missing {n}" for n in sorted(set(want) - have)]
    problems += [f"not in SENSES.tsv: {n}" for n in sorted(have - set(want))]
    for n in sorted(set(want) & have):
        with open(os.path.join(manifest_dir, n), encoding="utf-8") as f:
            if f.read() != want[n]:
                problems.append(f"differs from SENSES.tsv: {n}")
    return problems


def write(tsv_path: str = TSV, manifest_dir: str = MANIFEST_DIR) -> list[str]:
    with open(tsv_path, encoding="utf-8") as f:
        files = generate(f.read())
    os.makedirs(manifest_dir, exist_ok=True)
    for n in os.listdir(manifest_dir):
        if n.endswith(".interop.json") and n not in files:
            os.remove(os.path.join(manifest_dir, n))
    for n, text in files.items():
        with open(os.path.join(manifest_dir, n), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return sorted(files)


def load(manifest_dir: str = MANIFEST_DIR) -> list[Manifest]:
    out = []
    for n in sorted(os.listdir(manifest_dir)):
        if n.endswith(".interop.json"):
            p = os.path.join(manifest_dir, n)
            with open(p, encoding="utf-8") as f:
                m = Manifest.from_dict(json.load(f))
            m.source = p
            if m.sense:
                out.append(m)
    return out


def match(manifests: list, kinds: list, ext: str = "") -> list[dict]:
    """Every sense whose accepted kinds meet `kinds`, cheapest budget first.

    A manifest that names extensions (`match_ext`) matches only items with one
    of them. The result lists why each one matched.
    """
    have = set(kinds)
    rows = []
    for m in manifests:
        s = m.sense
        hit = sorted(have & set(s.get("accepts", [])))
        if not hit:
            continue
        exts = s.get("match_ext") or []
        if exts and ext.lower() not in exts:
            continue
        rows.append({"tool": m.organ, "on": hit, "runnable": bool(s.get("run")),
                     "budget": s.get("budget", {}), "manifest": m})
    rows.sort(key=lambda r: (r["budget"].get("time_s") or 1e9, r["tool"]))
    return rows
