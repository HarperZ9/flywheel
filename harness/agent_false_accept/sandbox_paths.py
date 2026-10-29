"""sandbox_paths.py -- spell a path the way the mock workspace stores it."""
from __future__ import annotations

ROOT = "/workspace"


def norm(raw: str) -> str:
    """Workspace-relative path, or 'outside:<path>' for anything beyond it."""
    p = str(raw).strip().strip("'\"").replace("\\", "/")
    if p.startswith(ROOT):
        p = p[len(ROOT):]
    elif p.startswith(("/", "~", "$HOME")):
        return "outside:" + p
    parts: list[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return "outside:" + p
            parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)
