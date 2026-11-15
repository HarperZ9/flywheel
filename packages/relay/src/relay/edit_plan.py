"""edit_plan.py -- transactional multi-file hash-anchored edits.

A plan is a list of ops, each addressing lines by the anchors a `hashed` read
emits (see hashline.py). The batch is all-or-nothing: every anchor is resolved
against the current files first, and if any is stale, ambiguous, or overlaps
another op in the same file, nothing is written. Each op yields a re-derivable
receipt (its resolved line, that line's pre-image text, and the anchor the model
used), so a stranger can recompute the anchor and confirm the edit landed on
exactly that line of that file version. Pure line math; the executor owns IO.
"""
from __future__ import annotations

from .hashline import as_lines, resolve_anchor


def resolve_op(lines: list, op: dict) -> "tuple[dict | None, str | None]":
    """Resolve one op against `lines` (from splitlines(keepends=True)) to a half-open
    line span plus its receipt, or (None, error). An insert is a zero-width span."""
    at, end, after = op.get("at"), op.get("end"), op.get("after")
    new = op.get("new", "")
    if after:
        i, err = resolve_anchor(lines, after)
        if err:
            return None, err
        return {"lo": i + 1, "hi": i + 1, "mode": "insert", "new": new,
                "anchor": after, "line": i + 1, "pre_image": lines[i].rstrip("\r\n")}, None
    if at:
        i, err = resolve_anchor(lines, at)
        if err:
            return None, err
        j = i
        if end:
            j, err = resolve_anchor(lines, end)
            if err:
                return None, err
            if j < i:
                return None, "'end' anchor precedes 'at'"
        return {"lo": i, "hi": j + 1, "mode": ("delete" if new == "" else "replace"),
                "new": new, "anchor": at, "line": i + 1, "pre_image": lines[i].rstrip("\r\n")}, None
    return None, "op needs 'at' or 'after'"


def check_overlaps(edits: list) -> "str | None":
    """None, or an error when two ops on one file touch overlapping lines. Ops are
    half-open [lo, hi) ranges; an insert is zero-width. Two ops anchored to the same
    start are refused as ambiguous, which keeps the batch fail-closed."""
    cover_hi = -1
    prev_lo = -2
    for e in sorted(edits, key=lambda e: (e["lo"], e["hi"])):
        if e["lo"] < cover_hi or e["lo"] == prev_lo:
            return f"op {e['op_index']} overlaps an earlier op in the same file"
        cover_hi = max(cover_hi, e["hi"])
        prev_lo = e["lo"]
    return None


def apply_edits(lines: list, edits: list) -> list:
    """Return new lines with all edits applied. Edits must be overlap-free. Applied
    bottom-up so earlier edits do not shift later line indices."""
    out = list(lines)
    for e in sorted(edits, key=lambda e: e["lo"], reverse=True):
        if e["mode"] == "insert":
            i = e["lo"] - 1
            if not out[i].endswith(("\n", "\r")):     # keep a separator at EOF
                out[i] += "\n"
            out[e["lo"]:e["lo"]] = as_lines(e["new"], "\n")
        else:
            j = e["hi"] - 1
            nl = "\n" if out[j].endswith("\n") else ""   # preserve a no-EOL final line
            out[e["lo"]:e["hi"]] = as_lines(e["new"], nl)
    return out


def build_plan(resolve_path, read_text, ops: list) -> "tuple[tuple | None, str | None]":
    """Validate a whole plan and compute its writes WITHOUT touching disk, so the
    batch stays all-or-nothing: the caller writes the returned pairs only if there is
    no error. resolve_path(rel) -> abspath or None (sandbox); read_text(abspath) ->
    str or None (missing). Returns ((writes, receipt), None) or (None, error), where
    writes is [(abspath, new_text)] and receipt is the re-derivable per-op record."""
    files: dict = {}
    for k, op in enumerate(ops):
        if not isinstance(op, dict) or not op.get("path"):
            return None, f"op {k}: missing 'path'"
        p = resolve_path(op["path"])
        if p is None:
            return None, f"op {k}: path {op['path']!r} escapes root"
        if p not in files:
            text = read_text(p)
            if text is None:
                return None, f"op {k}: file {op['path']!r} not found"
            files[p] = {"rel": op["path"], "lines": text.splitlines(keepends=True), "edits": []}
        edit, err = resolve_op(files[p]["lines"], op)
        if err:
            return None, f"op {k} ({op['path']}): {err}"
        edit["op_index"], edit["path"] = k, op["path"]
        files[p]["edits"].append(edit)
    for fp in files.values():
        err = check_overlaps(fp["edits"])
        if err:
            return None, f"{fp['rel']}: {err}"
    writes, receipt = [], []
    for p, fp in files.items():
        writes.append((p, "".join(apply_edits(fp["lines"], fp["edits"]))))
        for e in fp["edits"]:
            receipt.append({"path": e["path"], "op": e["op_index"], "mode": e["mode"],
                            "anchor": e["anchor"], "line": e["line"],
                            "pre_image": e["pre_image"][:200]})
    return (writes, receipt), None
