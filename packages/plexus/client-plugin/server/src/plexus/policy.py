"""policy.py: the boundary fanout runs inside, read from data.

`sense_data/policy.json` says which kinds a tool may run on, who may use the
network, which paths a call may name, where it may write and how much time and
memory it may take. `refusals` is called for every planned tool before
anything starts; a non-empty answer means the tool is not launched and the
reasons go into the bundle. The checks are on the declared manifest and on the
resolved invocation (argv, working folder, environment, MCP arguments). They are
not an operating-system sandbox: a tool that opens a socket or a path it never
names on its command line is not stopped by this file. Time and memory are
enforced on the running process by plexus.budget.
"""
from __future__ import annotations

import hashlib
import json
import os

from .kinds import KINDS
from .senses import SENSES_DIR

SCHEMA = "plexus.senses-policy/1"
POLICY_PATH = os.path.join(SENSES_DIR, "policy.json")


class PolicyError(ValueError):
    """The policy file itself is malformed."""


def load(path: str = POLICY_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    pol = json.loads(text)
    if pol.get("schema") != SCHEMA:
        raise PolicyError(f"policy schema {pol.get('schema')!r} != {SCHEMA}")
    for key in ("defaults", "ceiling", "kinds", "refuse_tools", "read_paths", "write_paths"):
        if key not in pol:
            raise PolicyError(f"policy lacks {key!r}")
    unknown = set(pol["kinds"].get("allowed", [])) - set(KINDS)
    if unknown:
        raise PolicyError(f"policy names kinds outside the vocabulary: {sorted(unknown)}")
    pol["sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return pol


def budget(pol: dict, sense: dict) -> dict:
    """The manifest's budget, with the policy default where it names none."""
    b = sense.get("budget") or {}
    return {"time_s": float(b.get("time_s") or pol["defaults"]["time_s"]),
            "memory_mb": int(b.get("memory_mb") or pol["defaults"]["memory_mb"])}


def _inside(path: str, roots: list) -> bool:
    p = os.path.normcase(os.path.realpath(path))
    for r in roots:
        r = os.path.normcase(os.path.realpath(r))
        if p == r or p.startswith(r.rstrip("\\/") + os.sep):
            return True
    return False


def _named_paths(inv: dict) -> list:
    """Absolute paths a resolved invocation names (not the program itself).

    An MCP server launch line from the local config is the operator's own
    setting and is not checked; one declared in a manifest is.
    """
    vals = list(inv.get("argv", [])[1:])
    if inv.get("launch_source") == "manifest":
        vals += list(inv.get("launch", [])[1:])
    vals += list((inv.get("env") or {}).values())
    vals += [v for v in (inv.get("args") or {}).values() if isinstance(v, str)]
    out = []
    for v in vals:
        v = str(v)
        if len(v) < 4096 and "\n" not in v and os.path.isabs(v):
            out.append(v)
    return out


def refusals(pol: dict, manifest, on_kinds: list, inv: "dict | None",
             grants: "dict | None" = None) -> list[str]:
    """Reasons this tool may not run on this item (empty = it may)."""
    grants = grants or {}
    s = manifest.sense
    why = []
    if manifest.organ in pol["refuse_tools"]:
        why.append(f"refused by policy: {pol['refuse_tools'][manifest.organ]}")
    allowed = set(pol["kinds"].get("allowed", []))
    need = pol["kinds"].get("need_grant", {})
    for k in on_kinds:
        if k in need and k not in set(grants.get("kinds", [])):
            why.append(f"kind {k!r} needs a grant: {need[k]}")
        elif k not in allowed and k not in need:
            why.append(f"kind {k!r} is not allowed")
    if s.get("network") and manifest.organ not in set(grants.get("network", [])):
        why.append("uses the network; this call did not grant it")
    b, ceil = budget(pol, s), pol["ceiling"]
    if b["time_s"] > ceil["time_s"]:
        why.append(f"asks {b['time_s']:g} s; the ceiling is {ceil['time_s']} s")
    if b["memory_mb"] > ceil["memory_mb"]:
        why.append(f"asks {b['memory_mb']} MB; the ceiling is {ceil['memory_mb']} MB")
    if inv is None:
        return why
    out = inv.get("out", "")
    for w in s.get("writes", []):
        target = w.replace("{out}", out)
        if not out or not _inside(target, [out]):
            why.append(f"writes outside its output folder: {w}")
    readable = [p for p in [inv.get("item_path"), inv.get("root"), out] if p]
    for p in _named_paths(inv):
        if not _inside(p, readable):
            why.append(f"names a path outside the item, its root and its output: {p}")
    return why
