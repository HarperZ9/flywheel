"""wrapper_scaffold_hook.py -- the per-message scaffold for ANY wrapper.

A harness that is not Flywheel (Claude Code, a CI bot, any agent shell)
mounts this as a prompt hook and inherits the same guarantee the
gateway's own routes carry: every source the user's message names is
frozen with a hash BEFORE the model works, and the manifest is injected
back into the turn as context.

Protocol (Claude Code UserPromptSubmit, and anything shaped like it):
reads a JSON event on stdin, finds the prompt text, extracts URLs,
freezes each through the local gateway's /api/snapshot, and prints a
compact provenance manifest to stdout (which the wrapper injects as
context). Fails OPEN and silent: a dead gateway or a promptless event
prints nothing and exits 0 -- the scaffold must never cost a turn.

Mount (Claude Code settings.json):
  "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",
    "command": "python <abspath>/scripts/hooks/wrapper_scaffold_hook.py"}]}]}
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request

GATEWAY = "http://127.0.0.1:8799"
_URL = re.compile(r"https?://[^\s)\]>\"']+")
_MAX = 5


def _prompt_from(event: dict) -> str:
    for key in ("prompt", "user_prompt", "message", "input"):
        v = event.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _freeze(url: str) -> "dict | None":
    body = json.dumps({"url": url}).encode()
    req = urllib.request.Request(
        GATEWAY + "/api/snapshot", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        doc = json.loads(r.read().decode())
    sha = str(doc.get("sha256", ""))
    return {"url": url, "sha256": sha} if len(sha) == 64 else None


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    urls = list(dict.fromkeys(_URL.findall(_prompt_from(event))))[:_MAX]
    if not urls:
        return 0
    frozen, degraded = [], []
    for u in urls:
        u = u.rstrip(".,;")
        try:
            doc = _freeze(u)
            (frozen.append(doc) if doc else
             degraded.append({"url": u, "reason": "no hash returned"}))
        except Exception as e:
            degraded.append({"url": u, "reason": type(e).__name__})
    if not frozen and not degraded:
        return 0
    lines = ["[scaffold] sources named in this message, frozen before work:"]
    lines += [f"  frozen  {f['url']}  sha256:{f['sha256']}" for f in frozen]
    lines += [f"  degraded  {d['url']}  ({d['reason']}; perception failed, "
              "named not faked)" for d in degraded]
    lines.append("[scaffold] cite by byte range against these hashes; "
                 "re-fetchable via the local gateway snapshot store")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
