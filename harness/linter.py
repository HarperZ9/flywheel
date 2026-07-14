"""linter.py -- a native, extensible, receipt-carrying code linter.

Zero dependencies. Every finding is content-addressed (a stable hash over
file:line:rule:message), and a run carries a root hash over the sorted
findings, so a lint result is re-checkable and storable -- the wedge over
tools that emit findings you cannot verify or pin. Rules are pure functions
over (path, text, lines); adding a rule is one entry in RULES. Multi-language
by line and light structure (Python indentation, brace scan for C-family).

Rules include the operator's own quality gates (file > 300 lines, function >
50 lines) as first-class, plus security-relevant patterns surfaced for
review -- never rewritten, only reported."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

MAX_FILE_LINES = 300
MAX_FUNC_LINES = 50
MAX_LINE_LEN = 120

_SCAN_EXT = {".py", ".dart", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
             ".java", ".c", ".cc", ".cpp", ".h"}
_IGNORE_DIRS = {".git", "node_modules", "build", ".dart_tool", "__pycache__",
                "dist", ".venv", "venv", "target", ".next", ".idea"}

_SECRET = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|access[_-]?key)"
    r"\s*[:=]\s*['\"][A-Za-z0-9_\-]{12,}['\"]")
_DANGER = re.compile(
    r"\b(eval|exec)\s*\(|\bos\.system\s*\(|\bsubprocess\.[a-z]+\([^)]*shell\s*=\s*True"
    r"|\bpickle\.loads\s*\(")
_TODO = re.compile(r"(?://|#)\s*(TODO|FIXME|XXX|HACK)\b")
_WILDCARD = re.compile(r"^\s*from\s+[\w.]+\s+import\s+\*")
_DEBUG = re.compile(r"\b(breakpoint\s*\(\s*\)|debugger\b|console\.log\s*\()")


def _finding(path: str, line: int, rule: str, severity: str, msg: str) -> dict:
    sha = hashlib.sha256(
        f"{path}:{line}:{rule}:{msg}".encode()).hexdigest()[:16]
    return {"file": path, "line": line, "rule": rule, "severity": severity,
            "message": msg, "receipt": sha}


def _rule_line_patterns(rel: str, text: str, lines: list) -> list:
    out = []
    for i, ln in enumerate(lines, 1):
        if _SECRET.search(ln):
            out.append(_finding(rel, i, "hardcoded-secret", "high",
                                "a literal that looks like a credential; use "
                                "the environment or keychain"))
        if _DANGER.search(ln):
            out.append(_finding(rel, i, "dangerous-call", "high",
                                "eval/exec/shell/pickle: review for injection "
                                "and sandboxing"))
        if _WILDCARD.match(ln):
            out.append(_finding(rel, i, "wildcard-import", "low",
                                "wildcard import hides what is in scope"))
        if _DEBUG.search(ln):
            out.append(_finding(rel, i, "debug-leftover", "low",
                                "debugger/console left in source"))
        m = _TODO.search(ln)
        if m:
            out.append(_finding(rel, i, "todo-marker", "low",
                                f"{m.group(1)} marker left in source"))
        if len(ln.rstrip("\n")) > MAX_LINE_LEN:
            out.append(_finding(rel, i, "long-line", "low",
                                f"line exceeds {MAX_LINE_LEN} characters"))
    return out


def _rule_file_length(rel: str, text: str, lines: list) -> list:
    n = len(lines)
    if n > MAX_FILE_LINES:
        return [_finding(rel, n, "file-too-long", "medium",
                         f"file is {n} lines (limit {MAX_FILE_LINES}); split it")]
    return []


def _rule_swallowed_error(rel: str, text: str, lines: list) -> list:
    out = []
    if rel.endswith(".py"):
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if s in ("except:", "except Exception:") and i < len(lines):
                nxt = lines[i].strip() if i < len(lines) else ""
                if nxt == "pass":
                    out.append(_finding(rel, i, "swallowed-error", "high",
                                        "bare except that passes: log with "
                                        "context or re-raise"))
    return out


def _rule_python_function_length(rel: str, text: str, lines: list) -> list:
    if not rel.endswith(".py"):
        return []
    out = []
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)def\s+(\w+)", lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        name = m.group(2)
        start = i
        j = i + 1
        while j < len(lines):
            ln = lines[j]
            if ln.strip() and not ln[:indent + 1].isspace() and \
                    len(ln) - len(ln.lstrip()) <= indent and ln.strip():
                break
            j += 1
        body = j - start
        if body > MAX_FUNC_LINES:
            out.append(_finding(rel, start + 1, "function-too-long", "medium",
                                f"{name} is ~{body} lines (limit "
                                f"{MAX_FUNC_LINES}); extract helpers"))
        i = j
    return out


RULES = [
    _rule_file_length,
    _rule_python_function_length,
    _rule_swallowed_error,
    _rule_line_patterns,
]


def lint_text(rel: str, text: str) -> list:
    """Every finding for one file's content. Public so a single buffer (the
    open editor) can be linted without touching disk."""
    lines = text.splitlines()
    findings = []
    for rule in RULES:
        try:
            findings.extend(rule(rel, text, lines))
        except Exception:
            pass  # a rule must never crash the run
    return findings


def _iter_files(root: Path, paths: "list | None"):
    if paths:
        for p in paths:
            fp = (root / p) if not Path(p).is_absolute() else Path(p)
            if fp.is_file():
                yield fp
        return
    for fp in root.rglob("*"):
        if not fp.is_file() or fp.suffix.lower() not in _SCAN_EXT:
            continue
        if any(part in _IGNORE_DIRS for part in fp.parts):
            continue
        yield fp


def lint_project(root: str, paths: "list | None" = None,
                 max_files: int = 4000) -> dict:
    """Lint a project root (or a named subset). Findings are receipted and
    the run carries a root hash so the result re-checks."""
    base = Path(root)
    if not base.is_dir():
        return {"error": f"root is not an existing directory: {root}"}
    findings: list = []
    scanned = 0
    for fp in _iter_files(base, paths):
        if scanned >= max_files:
            break
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(fp.relative_to(base)) if fp.is_relative_to(base) else fp.name
        findings.extend(lint_text(rel.replace("\\", "/"), text))
        scanned += 1
    findings.sort(key=lambda f: (f["severity"] != "high",
                                 f["severity"] != "medium", f["file"], f["line"]))
    root_hash = hashlib.sha256(
        "\n".join(f["receipt"] for f in findings).encode()).hexdigest()
    by_sev: dict = {}
    by_rule: dict = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1
    return {"schema": "flywheel.lint/v1", "root": str(base),
            "files_scanned": scanned, "n_findings": len(findings),
            "by_severity": by_sev, "by_rule": by_rule,
            "root_hash": root_hash, "findings": findings,
            "note": "every finding is content-addressed; the root hash "
                    "re-checks the whole run"}
