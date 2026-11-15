"""watch.py — file-marker watch mode: drop a comment in ANY file, relay acts on it.

A named, real gap versus aider (whose stand-out ergonomic feature is exactly
this — no editor plugin needed, so it works the same in vim, Notepad, or a hex
editor). This is relay's version, with one deliberate difference: the marker's
fix goes through the SAME gated tool loop and witnessed ledger as every other
relay run. The model is told to remove the marker itself via edit_file once it
has acted, so even a change triggered by typing a comment — not a prompt — is
never a bypass of the accountability the rest of relay provides.
"""
from __future__ import annotations

import os

from .local_loop import run_agent
from .local_repomap import _IGNORE

DEFAULT_MARKER = "RELAY:"
_CONTEXT_LINES = 6            # lines of surrounding code shown per marker
_MAX_FILE_BYTES = 2_000_000    # skip anything implausible as a text source file


def find_markers(root: str, *, marker: str = DEFAULT_MARKER) -> list:
    """Every occurrence of `marker` in a text file under root, with context.
    Binary/oversized/undecodable files are skipped, never guessed at."""
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE)
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            try:
                if os.path.getsize(path) > _MAX_FILE_BYTES:
                    continue
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(lines):
                if marker not in line:
                    continue
                instruction = line.split(marker, 1)[1].strip()
                if not instruction:
                    continue
                lo, hi = max(0, i - _CONTEXT_LINES), min(len(lines), i + _CONTEXT_LINES + 1)
                hits.append({"path": os.path.relpath(path, root), "line": i + 1,
                            "instruction": instruction, "context": "".join(lines[lo:hi])})
    return hits


def _goal_for(hit: dict, marker: str) -> str:
    return (f"In {hit['path']} near line {hit['line']}, a comment asks:\n"
           f"\"{hit['instruction']}\"\n\nSurrounding code:\n{hit['context']}\n\n"
           f"Do what the comment asks. When you are done, use edit_file to remove "
           f"the marker comment line (the one containing \"{marker}\") from "
           f"{hit['path']} so it is not re-triggered.")


def run_watch_once(agent, executor, *, marker: str = DEFAULT_MARKER, max_steps: int = 6,
                   ledger_factory=None) -> list:
    """One scan-and-act pass: find every marker under executor.root and run each
    as its own agent goal with its own witnessed ledger. A marker the model
    successfully removes will not re-fire on the next pass; one it fails to
    remove (e.g. --allow-write was off) is reported and will re-fire, honestly."""
    from .local_session import SessionLedger
    make_ledger = ledger_factory or SessionLedger
    results = []
    for hit in find_markers(executor.root, marker=marker):
        ledger = make_ledger()
        res = run_agent(agent, _goal_for(hit, marker), executor, ledger, max_steps=max_steps)
        results.append({"path": hit["path"], "line": hit["line"], "instruction": hit["instruction"],
                        "final": res["final"], "verified": res["verified"],
                        "checkpoint": res["checkpoint"]})
    return results
