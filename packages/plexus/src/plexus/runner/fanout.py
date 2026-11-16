"""fanout.py: send one item to every tool that accepts it, and keep every answer.

  plan  = which sense manifests match the item's kinds, and for each one
          whether it will run, or why not (refused by policy, not runnable
          from a command line, or unavailable on this machine)
  run   = each runnable tool in turn, under its time and memory budget
  bundle= one folder: each tool's stdout and stderr, and bundle.json with the
          status, time, peak memory and error of every tool, plus a receipt

A tool that fails, times out, is refused or cannot be reached is a row in the
bundle with its reason. Nothing is dropped. Tools run one at a time.

Machine-specific settings live in a local config (never in the repository):
{"roots": {"superframe": DIR, "portfolio-site": DIR}, "python": EXE,
 "node": EXE, "mcp_servers": {name: {"command": EXE, "args": [...]}},
 "mcp_config": PATH}. `mcp_config` points at a Claude-style JSON whose
`mcpServers` are read (never written).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from . import budget as _budget
from .. import policy as _policy
from .. import senses as _senses
from ..kinds import detect
from ..manifest import content_hash

SCHEMA = "plexus.fanout/1"
RECEIPT_SCHEMA = "plexus.fanout-receipt/1"
TEXT_LIMIT = 200_000
_SRC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_config(path: "str | None") -> dict:
    path = path or os.environ.get("PLEXUS_SENSES_CONFIG") or os.path.expanduser("~/.plexus/senses.json")
    cfg = {"roots": {}, "mcp_servers": {}, "source": ""}
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
        cfg["source"] = path
    servers = dict(cfg.get("mcp_servers") or {})
    mc = cfg.get("mcp_config")
    if mc and os.path.isfile(os.path.expanduser(mc)):
        with open(os.path.expanduser(mc), encoding="utf-8") as f:
            data = json.load(f)
        found = dict(data.get("mcpServers") or {})
        for proj in (data.get("projects") or {}).values():
            for k, v in (proj.get("mcpServers") or {}).items():
                found.setdefault(k, v)
        for k, v in found.items():
            servers.setdefault(k, v)
    cfg["mcp_servers"] = servers
    return cfg


def _item_text(item: str) -> str:
    if os.path.isfile(item):
        with open(item, "rb") as f:
            return f.read(TEXT_LIMIT).decode("utf-8", "replace")
    return item[:TEXT_LIMIT]


def _is_text(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    with open(path, "rb") as f:
        head = f.read(8192)
    if b"\x00" in head:
        return False
    return head.decode("utf-8", "replace").count("�") <= len(head) // 100


def _fill(value, subs: dict):
    if isinstance(value, str):
        return re.sub(r"\{(item|text|out|python|node)\}", lambda m: subs[m.group(1)], value)
    if isinstance(value, list):
        return [_fill(v, subs) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, subs) for k, v in value.items()}
    return value


def resolve(manifest, item: str, out: str, cfg: dict) -> "tuple[dict | None, str]":
    """The concrete invocation for this item, or (None, why it cannot run here)."""
    run = manifest.sense.get("run")
    if not run:
        return None, "not runnable: no command-line or MCP call for an item (see exact_call)"
    form = "path" if os.path.exists(item) else ("url" if re.match(r"^https?://", item, re.I) else "literal")
    forms = run.get("forms") or ["path"]
    if form not in forms:
        return None, f"not applicable: takes a {' or '.join(forms)}, the item is a {form}"
    if "{text}" in json.dumps(run) and form == "path" and not _is_text(item):
        return None, "not applicable: takes text, the item is binary"
    subs = {"item": os.path.abspath(item) if os.path.exists(item) else item,
            "text": _item_text(item) if "{text}" in json.dumps(run) else "",
            "out": out, "python": cfg.get("python") or sys.executable,
            "node": cfg.get("node") or "node"}
    root = ""
    if run.get("root"):
        root = (cfg.get("roots") or {}).get(run["root"], "")
        if not root or not os.path.isdir(root):
            return None, f"unavailable: root {run['root']!r} is not set in the local config"
    inv = {"out": out, "root": root, "item_path": subs["item"] if os.path.exists(item) else ""}
    if "cli" in run:
        inv["argv"] = _fill(run["cli"], subs)
        inv["cwd"] = os.path.join(root, run.get("cwd", "")) if root else None
        inv["env"] = _fill(run.get("env") or {}, subs)
        return inv, ""
    if run.get("launch"):
        inv["launch"], inv["launch_source"] = _fill(run["launch"], subs), "manifest"
    else:
        srv = cfg["mcp_servers"].get(run["mcp"])
        if not srv:
            return None, f"unavailable: MCP server {run['mcp']!r} is not in the local config"
        inv["launch"], inv["launch_source"] = [srv["command"], *srv.get("args", [])], "config"
    inv["args"] = _fill(run.get("args") or {}, subs)
    inv["tool"] = run["tool"]
    inv["cwd"] = root or None
    return inv, ""


def plan(item: str, *, extra_kinds=(), cfg=None, pol=None, grants=None, out_root=".",
         manifests=None) -> dict:
    cfg = cfg if cfg is not None else load_config(None)
    pol = pol or _policy.load()
    found = detect(item)
    kinds = list(dict.fromkeys(found["kinds"] + list(extra_kinds)))
    ext = os.path.splitext(item)[1].lower() if os.path.isfile(item) else ""
    rows = []
    mans = _senses.load() if manifests is None else manifests
    for hit in _senses.match(mans, kinds, ext):
        m = hit["manifest"]
        out = os.path.join(out_root, m.organ)
        inv, why = resolve(m, item, out, cfg)
        refused = _policy.refusals(pol, m, hit["on"], inv, grants)
        if inv is None and why.startswith("not applicable"):
            refused = []                  # the tool does not take this form; policy is moot
        status = "refused" if refused else ("planned" if inv else why.split(":")[0])
        rows.append({"tool": m.organ, "on": hit["on"], "status": status,
                     "reason": "; ".join(refused) if refused else ("" if inv else why),
                     "budget": _policy.budget(pol, m.sense), "manifest_sha256": content_hash(m),
                     "invocation": inv, "_manifest": m})
    return {"schema": SCHEMA, "item": item, "kinds": kinds, "detected": found,
            "policy_sha256": pol["sha256"], "config": cfg.get("source", ""), "tools": rows}


def _tail(path: str, n: int = 1500) -> str:
    with open(path, "rb") as f:
        data = f.read()
    return data[-n:].decode("utf-8", "replace").strip()


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _execute(row: dict, pol: dict) -> dict:
    inv, b = row["invocation"], row["budget"]
    os.makedirs(inv["out"], exist_ok=True)
    so, se = os.path.join(inv["out"], "stdout.txt"), os.path.join(inv["out"], "stderr.txt")
    if "argv" in inv:
        argv, env = inv["argv"], inv.get("env")
    else:
        spec = os.path.join(inv["out"], "mcp-call.json")
        with open(spec, "w", encoding="utf-8") as f:
            json.dump({"launch": inv["launch"], "cwd": inv.get("cwd"), "tool": inv["tool"],
                       "args": inv["args"], "timeout_s": b["time_s"]}, f, indent=2)
        argv = [sys.executable, "-m", "plexus.runner.mcp_call", spec]
        env = {"PYTHONPATH": _SRC + os.pathsep + os.environ.get("PYTHONPATH", "")}
    r = _budget.run(argv, cwd=inv.get("cwd"), env=env, time_s=b["time_s"],
                    memory_mb=b["memory_mb"], stdout_path=so, stderr_path=se)
    cap = int(pol.get("outputs", {}).get("max_stdout_mb", 64)) * 1024 * 1024
    if os.path.getsize(so) > cap:
        with open(so, "r+b") as f:
            f.truncate(cap)
        r["error"] = (r["error"] + "; " if r["error"] else "") + f"stdout cut at {cap // 1048576} MB"
    if r["timed_out"]:
        status = "timeout"
    elif r["exit_code"] == 0 and not r["error"]:
        status = "ok" if os.path.getsize(so) else "empty"
    else:
        status = "failed"
    err = r["error"] or ("" if status == "ok" else _tail(se) or f"exit code {r['exit_code']}, no output")
    return {"status": status, "exit_code": r["exit_code"], "seconds": r["seconds"],
            "peak_mb": r["peak_mb"], "memory_exceeded": r["memory_exceeded"], "error": err,
            "stdout": os.path.relpath(so, os.path.dirname(inv["out"])),
            "stdout_sha256": _sha(so), "stdout_bytes": os.path.getsize(so)}


def _body_sha(bundle: dict) -> str:
    body = {k: v for k, v in bundle.items() if k != "receipt"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def fanout(item: str, out_dir: str, *, extra_kinds=(), cfg=None, grants=None,
           dry_run: bool = False, only=None, manifests=None, policy_path=None) -> dict:
    """Plan, run every runnable match, write `bundle.json` under a new folder in out_dir."""
    pol = _policy.load(policy_path) if policy_path else _policy.load()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.basename(item.rstrip("/\\")) or "item")[:60]
    folder = os.path.abspath(os.path.join(out_dir, f"{stem}-{stamp}"))
    p = plan(item, extra_kinds=extra_kinds, cfg=cfg, pol=pol, grants=grants, out_root=folder,
             manifests=manifests)
    t0 = time.perf_counter()
    for row in p["tools"]:
        if only and row["tool"] not in only and row["status"] == "planned":
            row["status"], row["reason"] = "skipped", "not in --only"
        if row["status"] == "planned" and not dry_run:
            row.update(_execute(row, pol))
        row.pop("_manifest", None)
    p["seconds"] = round(time.perf_counter() - t0, 3)
    p["item_sha256"] = _sha(item) if os.path.isfile(item) else hashlib.sha256(item.encode()).hexdigest()
    p["counts"] = {s: sum(1 for r in p["tools"] if r["status"] == s)
                   for s in sorted({r["status"] for r in p["tools"]})}
    p["receipt"] = {"schema": RECEIPT_SCHEMA,
                    "manifest_shas": {r["tool"]: r["manifest_sha256"] for r in p["tools"]},
                    "outputs": {r["tool"]: r["stdout_sha256"] for r in p["tools"] if "stdout_sha256" in r},
                    "policy_sha256": p["policy_sha256"], "bundle_sha256": _body_sha(p)}
    if not dry_run:
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "bundle.json"), "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2, ensure_ascii=False)
        p["bundle"] = os.path.join(folder, "bundle.json")
    return p


def verify(bundle_path: str) -> dict:
    """Re-hash every output and the bundle body; report each mismatch."""
    with open(bundle_path, encoding="utf-8") as f:
        b = json.load(f)
    problems = []
    if _body_sha(b) != b.get("receipt", {}).get("bundle_sha256"):
        problems.append("bundle body changed since its receipt")
    base = os.path.dirname(bundle_path)
    for tool, sha in b.get("receipt", {}).get("outputs", {}).items():
        row = next((r for r in b["tools"] if r["tool"] == tool), {})
        path = os.path.join(base, row.get("stdout", ""))
        if not os.path.isfile(path) or _sha(path) != sha:
            problems.append(f"output of {tool} missing or changed")
    return {"verified": not problems, "problems": problems}
