"""rules.py -- layer 1: the versioned, digest-pinned deterministic rule pack.

The shipped pack lives beside this module (rules_v1.json). An owner overlay
may add rules and list allowed and owned hosts. It may not remove, soften or
redefine a shipped rule: the overlay is additive, so it can only add stops.
Evaluation is pure: same pack digest, same call, same hits. That is what lets
a stranger re-derive every layer-1 verdict from a record.
"""
from __future__ import annotations

import copy
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path

from .contract import BLOCK, HOLD, Hit, ProposedCall, RunContext, canonical_json, sha256_hex
from .normalize import Facts, extract, norm_path

_PACK_PATH = Path(__file__).with_name("rules_v1.json")
_MUTATES = re.compile(
    r"(>|\b(rm|del|mv|move|cp|copy|chmod|chown|icacls|attrib|tee|truncate|ren|rename|"
    r"Remove-Item|Set-Content|Out-File|Add-Content|Move-Item|Copy-Item)\b|\bsed\s+-i)",
    re.IGNORECASE)
_RULE_KEYS = {"id", "family", "action", "reason", "match"}


def _validate_rule(rule: dict) -> None:
    if set(rule) != _RULE_KEYS:
        raise ValueError(f"rule fields must be exactly {sorted(_RULE_KEYS)}")
    if rule["action"] not in (HOLD, BLOCK):
        raise ValueError("rule action must be HOLD or BLOCK")
    if not str(rule["id"]).startswith(str(rule["family"]) + "/"):
        raise ValueError("rule id must start with its family")
    if not isinstance(rule["match"], dict):
        raise ValueError("rule match must be an object")


def load_pack(overlay: dict | None = None, path: Path | None = None) -> dict:
    pack = json.loads((path or _PACK_PATH).read_text(encoding="utf-8"))
    for rule in pack["rules"]:
        _validate_rule(rule)
    if not overlay:
        return pack
    merged = copy.deepcopy(pack)
    shipped = {r["id"] for r in merged["rules"]}
    for rule in overlay.get("rules", []):
        _validate_rule(rule)
        if rule["id"] in shipped:
            raise ValueError(f"overlay may not redefine shipped rule {rule['id']}")
        merged["rules"].append(rule)
    merged["overlay_allow_hosts"] = sorted(str(h).lower() for h in overlay.get("allow_hosts", []))
    merged["overlay_owned_hosts"] = sorted(str(h).lower() for h in overlay.get("owned_hosts", []))
    return merged


def pack_digest(pack: dict) -> str:
    return sha256_hex(canonical_json(pack))


def _glob_any(paths: list, globs: list) -> bool:
    return any(fnmatchcase(p, g.lower()) for p in paths for g in globs)


def _under(path: str, root: str) -> bool:
    root = root.rstrip("/")
    return bool(root) and (path == root or path.startswith(root + "/"))


def _allowed_hosts(pack: dict, ctx: RunContext) -> set:
    return ({h.lower() for h in pack.get("default_allow_hosts", [])}
            | set(pack.get("overlay_allow_hosts", [])) | {h.lower() for h in ctx.allow_hosts})


def _owned_hosts(pack: dict, ctx: RunContext) -> set:
    return set(pack.get("overlay_owned_hosts", [])) | {h.lower() for h in ctx.owned_hosts}


def _unparseable(command: str) -> bool:
    from ..shell_parse import AdmissionError, walk_findings
    try:
        walk_findings(command)
    except AdmissionError:
        return True
    return False


def _paths_ok(m: dict, f: Facts, ctx: RunContext) -> bool:
    if "path_glob" in m:
        paths = [p for p in f.paths if not _glob_any([p], m.get("path_exclude", []))]
        if not _glob_any(paths, m["path_glob"]):
            return False
    if m.get("protected_paths"):
        roots = [norm_path(p, "") for p in ctx.protected_paths]
        if not any(_under(p, r) for p in f.paths for r in roots):
            return False
    if "command_mutates_path_glob" in m:
        if not (_MUTATES.search(f.command) and _glob_any(f.paths, m["command_mutates_path_glob"])):
            return False
    if m.get("paths_outside_workspace"):
        ws = norm_path(ctx.workspace, "") if ctx.workspace else ""
        if not ws or not any(not _under(p, ws) for p in f.paths):
            return False
    return True


def _text_ok(m: dict, call: ProposedCall, f: Facts) -> bool:
    if "tool_regex" in m and not re.search(m["tool_regex"], call.tool):
        return False
    if "command_regex" in m and not re.search(m["command_regex"], f.command, re.IGNORECASE):
        return False
    if "text_regex" in m and not re.search(m["text_regex"], f.text + "\n" + f.command):
        return False
    if m.get("unparseable_command") and not (f.command and _unparseable(f.command)):
        return False
    return True


def _matches(m: dict, pack: dict, call: ProposedCall, f: Facts, ctx: RunContext) -> bool:
    if "kinds" in m and f.kind not in m["kinds"]:
        return False
    if not (_paths_ok(m, f, ctx) and _text_ok(m, call, f)):
        return False
    if m.get("host_off_allowlist") and not set(f.hosts) - _allowed_hosts(pack, ctx):
        return False
    if m.get("host_unowned"):
        unowned = set(f.hosts) - _owned_hosts(pack, ctx) - _allowed_hosts(pack, ctx)
        if not unowned:
            return False
    if m.get("canary"):
        hay = f.text + "\n" + f.command
        if not any(tok and tok in hay for tok in ctx.canaries):
            return False
    return True


def evaluate(pack: dict, call: ProposedCall, ctx: RunContext) -> list:
    facts = extract(call, ctx)
    return [Hit(id=r["id"], family=r["family"], action=r["action"], reason=r["reason"], layer=1)
            for r in pack["rules"] if _matches(r["match"], pack, call, facts, ctx)]
