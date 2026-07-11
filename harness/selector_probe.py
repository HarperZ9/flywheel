"""selector_probe.py -- typed behavioral battery + clustering for oracle-free
selection (split from selector.py to keep each file under the size gate).

The "pre-decided world" as a probe: run each candidate on a fixed typed input
battery, fingerprint its behavior deterministically, and cluster by agreement.
Consensus is the largest productive cluster -- no learned model, no oracle, just
behavior on inputs the operating surface decides in advance. selector.py composes
these into the selection policy.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from .oracle import _kill_tree


# --- typed input battery (the "pre-decided world" as a behavioral probe) -------
# Per-parameter typed pools. Wrong-typed inputs make every candidate crash
# identically and erase the behavioral signal consensus needs; typed inputs the
# function can actually process are what let correct candidates diverge from
# wrong ones. Inferred per-parameter from the reference signature.
_INT_POOL = [0, 1, -1, 2, 3, 1, 4, 2, 5, 3, -2, 7]
_STR_POOL = ["", "a", "ab", "abba", "hello", "  ", "abc", "x y", "123", "a,b,c", "A", "z"]
_LIST_INT_POOL = [[], [1], [3, 1, 2], [1, 1, 2, 3], [5, 5], [0], [-1, 0, 1],
                  [10, 9, 8], [1, 2, 3, 4, 5], [7], [3, 3], [1, -1, 2, -2]]
_LIST_STR_POOL = [[], ["a"], ["b", "a"], ["x", "y", "z"], ["hello"], ["", "a"]]
_BOOL_POOL = [True, False, True, False, True, False, True, False, True, False, True, False]
_DICT_POOL = [{}, {"a": 1}, {"x": 0, "y": 1}, {"k": "v"}, {1: 2}, {"a": 1, "b": 2, "c": 3}]
_MATRIX_POOL = [[[1, 2], [3, 4]], [[1]], [[1, 2, 3]], [], [[0, 0], [0, 0]],
                [[1, 2], [3, 4], [5, 6]], [[7]], [[1, 0], [0, 1]], [[1, 2, 3], [4, 5, 6]],
                [[9, 8, 7], [6, 5, 4], [3, 2, 1]], [[-1, -2], [-3, -4]], [[100]]]
_MIXED_POOL = [0, 1, -1, 7, 2, [], [1], [3, 1, 2], [1, 1, 2, 3],
               "", "a", "abba", "hello", [0], [5, 5]]

_TYPE_POOLS = {
    "int": _INT_POOL, "float": _INT_POOL, "str": _STR_POOL,
    "list": _LIST_INT_POOL, "list_int": _LIST_INT_POOL, "list_str": _LIST_STR_POOL,
    "bool": _BOOL_POOL, "dict": _DICT_POOL, "matrix": _MATRIX_POOL, "mixed": _MIXED_POOL,
}

_NAME_LIST = {"nums", "arr", "array", "items", "lst", "seq", "values", "data",
              "numbers", "elements", "intervals", "ranges", "edges", "pairs",
              "replacement"}
_NAME_MATRIX = {"matrix", "grid", "board", "m", "mat", "rows"}
_NAME_STR = {"s", "text", "string", "word", "line", "name", "pattern", "fmt",
             "raw", "src", "header", "template", "expr"}
_NAME_INT = {"n", "k", "size", "count", "idx", "start", "stop", "index", "limit",
             "width", "bits", "base", "step"}
_NAME_DICT = {"mapping", "lookup", "table", "config", "kwargs"}


def _entry_def(solution, entry_point: str | None = None):
    """Resolve the target FunctionDef. With entry_point, pick that exact function
    (so a solution that defines helpers first is not misread by 'first def'); else
    default to the first top-level FunctionDef -- the convention task_curator uses."""
    defs = [n for n in _safe_parse(solution) if isinstance(n, ast.FunctionDef)]
    if entry_point:
        for n in defs:
            if n.name == entry_point:
                return n
    return defs[0] if defs else None


def fn_name(solution, entry_point: str | None = None) -> str | None:
    node = _entry_def(solution, entry_point)
    return node.name if node else None


def fn_arity(solution, entry_point: str | None = None) -> int | None:
    # Battery probes POSITIONALLY, so arity is the positional-parameter count.
    # Keyword-only / *args / **kwargs are not positionally probeable; a candidate
    # needing a required kwonly arg simply raises TypeError on the battery and is
    # (correctly) treated as non-productive -- graceful degradation, not a crash.
    node = _entry_def(solution, entry_point)
    return len(node.args.args) + len(node.args.posonlyargs) if node else None


def _safe_parse(solution):
    # solution_sig is the one selector input a caller can pass unchecked; every
    # non-parseable shape (None, non-str, null bytes, garbled source) degrades to
    # [] here so fn_name/fn_arity/infer_param_types never propagate a crash.
    if not isinstance(solution, str):
        return []
    try:
        return ast.parse(solution).body
    except (SyntaxError, ValueError):
        return []


def infer_param_types(solution, entry_point: str | None = None) -> list[str]:
    """Infer parameter types from annotations, else parameter-name heuristics."""
    node = _entry_def(solution, entry_point)
    if node is not None:
        types: list[str] = []
        for arg in node.args.args:
            ann = arg.annotation
            if isinstance(ann, ast.Name):
                types.append(ann.id.lower())
            elif isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name):
                if ann.value.id.lower() == "list":
                    inner = ann.slice
                    if isinstance(inner, ast.Name) and inner.id.lower() == "str":
                        types.append("list_str")
                    else:
                        types.append("list_int")
                else:
                    types.append("mixed")
            elif arg.arg in _NAME_LIST:
                types.append("list_int")
            elif arg.arg in _NAME_MATRIX:
                types.append("matrix")
            elif arg.arg in _NAME_STR:
                types.append("str")
            elif arg.arg in _NAME_INT:
                types.append("int")
            elif arg.arg in _NAME_DICT:
                types.append("dict")
            else:
                types.append("mixed")
        return types
    return []


def battery(arity: int, n: int = 12, param_types: list[str] | None = None) -> list[tuple]:
    """Type-aware input battery. Each parameter draws from its typed pool with a
    per-parameter offset so same-typed params do not receive identical values
    (which would erase the signal for functions like splice(items, start, stop))."""
    if not arity or arity < 1:
        arity = 1
    if not param_types:
        param_types = ["mixed"] * arity
    while len(param_types) < arity:
        param_types.append("mixed")
    out = []
    for i in range(n):
        row = []
        for j in range(arity):
            pool = _TYPE_POOLS.get(param_types[j], _MIXED_POOL)
            row.append(pool[(i + j * 3) % len(pool)])
        out.append(tuple(row))
    return out


SLOT_TIMEOUT = 3          # per-input deadline inside the probe (deterministic)
PROBE_BACKSTOP = 20       # whole-probe subprocess deadline (hard, tree-killed)


def _signature(candidate, fn: str, batt: list[tuple], workdir: Path,
               idx: int, slot_timeout: int = SLOT_TIMEOUT,
               backstop: int = PROBE_BACKSTOP):
    """Behavioral fingerprint: run fn on each battery input, record repr or
    exception type. A PER-INPUT deadline (slot_timeout) marks only the slow slot,
    so machine load can't flip a whole candidate's cluster membership run-to-run;
    a whole-probe backstop tree-kills a driver that hangs outside the loop.
    Unrunnable/backstopped candidates get a unique signature (never cluster)."""
    if not isinstance(candidate, str):
        return ("UNRUNNABLE", idx)          # non-string candidate never clusters
    try:
        workdir.mkdir(parents=True, exist_ok=True)   # every I/O step degrades, not crashes
        (workdir / "solution.py").write_text(candidate, encoding="utf-8")
    except Exception:
        return ("UNRUNNABLE", idx)
    # Build the driver by concatenation (only fn + batt are interpolated, both
    # trusted: fn is an ast-validated identifier, batt is repr of literals).
    driver = (
        "import json, threading, solution\n"
        "B = " + repr(batt) + "\n"
        "T = " + str(slot_timeout) + "\n"
        "out = []\n"
        "for a in B:\n"
        "    box = [None]\n"
        "    def work(a=a, box=box):\n"
        "        try:\n"
        "            box[0] = ('R', repr(solution." + fn + "(*a))[:200])\n"
        "        except Exception as e:\n"
        "            box[0] = ('E', type(e).__name__)\n"
        "    th = threading.Thread(target=work, daemon=True)\n"
        "    th.start(); th.join(T)\n"
        "    if th.is_alive():\n"
        "        out.append('SLOT_TIMEOUT')\n"
        "    elif box[0] is None:\n"
        "        out.append('WORKER_DIED')\n"
        "    elif box[0][0] == 'R':\n"
        "        out.append(box[0][1])\n"
        "    else:\n"
        "        out.append('EXC:' + box[0][1])\n"
        "print(json.dumps(out))\n")
    try:
        (workdir / "driver.py").write_text(driver, encoding="utf-8")
    except Exception:
        return ("UNRUNNABLE", idx)
    # PYTHONHASHSEED=0 pins set/dict iteration order so repr()-based signatures
    # are identical across processes -- otherwise the same candidate can land in
    # different clusters on different runs and selection stops being deterministic.
    try:
        proc = subprocess.Popen(
            [sys.executable, "driver.py"], cwd=workdir,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"})
    except Exception:
        return ("UNRUNNABLE", idx)
    # The backstop must DOMINATE the worst-case per-slot sum so it only catches a
    # hang OUTSIDE the loop (import, etc.), never pre-empt legitimate per-slot waits.
    effective_backstop = max(backstop, slot_timeout * len(batt) + 5)
    try:
        out, _ = proc.communicate(timeout=effective_backstop)
        if proc.returncode != 0:
            return ("UNRUNNABLE", idx)
        lines = out.decode("utf-8", "replace").strip().splitlines()
        if not lines:
            return ("UNRUNNABLE", idx)
        return tuple(json.loads(lines[-1]))
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return ("TIMEOUT", idx)
    except Exception:
        return ("UNRUNNABLE", idx)


def _productive(sig) -> bool:
    """A candidate that raises/hangs on every input (or won't run) is not
    agreeing; shared failure is not productive consensus. Needs >=1 real return
    value -- an exception marker or a per-slot timeout does not count."""
    if not isinstance(sig, tuple) or (sig and sig[0] in ("UNRUNNABLE", "TIMEOUT")):
        return False
    _control = ("SLOT_TIMEOUT", "WORKER_DIED")
    return any(isinstance(x, str) and not x.startswith("EXC:") and x not in _control
               for x in sig)


def _cluster_select(candidates: list[str], fn: str, arity: int, workdir: Path,
                    param_types: list[str] | None = None) -> tuple[int, float, float]:
    """Return (index, confidence, runner_up_confidence). confidence is the
    fraction in the winning PRODUCTIVE cluster; runner_up is the fraction in the
    next-largest productive cluster (0 if none). runner_up == confidence signals
    a TIE -- an ambiguous split the oracle-free path cannot honestly resolve."""
    n = len(candidates)
    if not fn or n == 0:
        return 0, 0.0, 0.0
    batt = battery(arity, param_types=param_types)
    sigs = [_signature(c, fn, batt, workdir / f"c{j}", j) for j, c in enumerate(candidates)]
    clusters: dict = {}
    for j, s in enumerate(sigs):
        clusters.setdefault(s, []).append(j)
    productive = [m for m in clusters.values() if _productive(sigs[m[0]])]
    if not productive:
        return 0, 0.0, 0.0
    productive.sort(key=lambda m: (len(m), -min(m)), reverse=True)
    best = productive[0]
    runner = len(productive[1]) / n if len(productive) > 1 else 0.0
    return min(best), len(best) / n, runner


def consensus_select(candidates: list[str], fn: str, arity: int, workdir: Path,
                     param_types: list[str] | None = None) -> tuple[int, float]:
    """Oracle-FREE selection. Return (index, confidence) = fraction of candidates
    in the winning behavioral cluster. Tie-break to the lowest index so the greedy
    candidate[0] is never lost to a wrong plurality. confidence 0.0 means no
    productive cluster. NOTE: confidence measures AGREEMENT, not correctness -- a
    wrong-but-agreeing majority scores high; `select()` adds the correlation and
    tie gates that keep that from being read as a confident accept."""
    idx, conf, _ = _cluster_select(candidates, fn, arity, workdir, param_types)
    return idx, conf


def _token_set(text: str) -> set:
    return set(text.split())


def _jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def max_correlation(texts: list[str]) -> float:
    m = 0.0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            m = max(m, _jaccard(texts[i], texts[j]))
    return m


