"""Arm C: FCA Block-Compressed Recall + Live BuildLang f64 Execution Tool.

Gives a small local model an explicit deterministic BuildLang compute tool
(`exec_buildlang_f64`) compiled and run via live PATH `buildc 1.15.0` (with a
strict allowlisted AST math fallback for offline CI runners without `buildc`).
Never leaks ground-truth answers. Pure stdlib Python, <= 240 LOC, <= 50 LOC/fn.
"""
from __future__ import annotations

import ast
import math
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import safe_program
from .eval_tasks import EvalTask, verify_task_output

_BLD_F64_RE = re.compile(r"(?i)BUILDLANG_F64\s*[:=]\s*(.+)")
_FENCE_RE = re.compile(r"```(?:buildlang|bld|rust|text)?\s*\n(.*?)```", re.S | re.I)
_BYPASS_RE = re.compile(
    r"(?i)\b(?:assert\s+(?:True|1\s*==\s*1)|skip_oracle\s*=\s*True|anygeometry\s*=\s*true)\b"
)
_SAFE_FUNCS: dict[str, Any] = {
    "pow": pow,
    "exp": math.exp,
    "sqrt": math.sqrt,
    "cbrt": math.cbrt,
    "log": math.log,
    "log2": math.log2,
    "abs": abs,
    "sin": math.sin,
    "cos": math.cos,
}


@dataclass(frozen=True)
class BuildLangExecResult:
    ok: bool
    value: float | None
    stdout: str
    error: str
    mode: str  # "buildc_live" | "sandbox_ast_f64" | "rejected"


def _eval_ast_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        val = _eval_ast_node(node.operand)
        return val if isinstance(node.op, ast.UAdd) else -val
    if isinstance(node, ast.BinOp):
        left, right = _eval_ast_node(node.left), _eval_ast_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            return left ** right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _SAFE_FUNCS.get(node.func.id)
        if fn is not None and not node.keywords:
            return float(fn(*(_eval_ast_node(a) for a in node.args)))
    raise ValueError("disallowed expression node")


def _wrap_expr_as_bld(expr: str) -> str:
    clean = expr.strip().rstrip(";")
    if "fn main" in clean:
        return clean
    # Normalize Python exponent operator `**` to BuildLang `pow()` only when absent
    return (
        "fn main() ~ Console {\n"
        f"    let ans: f64 = ({clean});\n"
        '    println!("{}", ans);\n'
        "}\n"
    )


def _run_live_buildc_f64(buildc_bin: str, source: str) -> BuildLangExecResult:
    with tempfile.TemporaryDirectory(prefix="jfc3p_f64_") as td:
        p = Path(td) / "calc.bld"
        p.write_text(source, encoding="utf-8")
        c_cmd, c_env = safe_program.launch([buildc_bin, "check", str(p)])
        chk = subprocess.run(c_cmd, env=c_env, capture_output=True, text=True, timeout=20)
        if chk.returncode != 0:
            err = (chk.stderr or chk.stdout or "buildc check failed").strip()[:260]
            return BuildLangExecResult(False, None, "", f"buildc_check_error: {err}", "buildc_live")
        r_cmd, r_env = safe_program.launch([buildc_bin, "run", str(p)])
        run = subprocess.run(r_cmd, env=r_env, capture_output=True, text=True, timeout=25)
        if run.returncode != 0:
            err = (run.stderr or run.stdout or "buildc run failed").strip()[:260]
            return BuildLangExecResult(False, None, "", f"buildc_run_error: {err}", "buildc_live")
        out = run.stdout.strip()
        last = out.splitlines()[-1].strip() if out else ""
        try:
            val = float(last)
        except ValueError:
            return BuildLangExecResult(False, None, out, f"non_float_stdout: {last!r}", "buildc_live")
        if not math.isfinite(val):
            return BuildLangExecResult(False, None, out, "non_finite_f64", "buildc_live")
        return BuildLangExecResult(True, val, out, "", "buildc_live")


def exec_buildlang_f64(expr_or_code: str, *, use_live_buildc: bool = True) -> BuildLangExecResult:
    """Deterministically execute a BuildLang f64 formula via live buildc or AST fallback."""
    raw = expr_or_code.strip()
    if not raw or _BYPASS_RE.search(raw):
        return BuildLangExecResult(False, None, "", "rejected_empty_or_bypass", "rejected")
    buildc_bin = safe_program.which("buildc") if use_live_buildc else None
    if buildc_bin:
        return _run_live_buildc_f64(buildc_bin, _wrap_expr_as_bld(raw))
    expr = raw.rstrip(";")
    if "fn main" in expr:
        m = re.search(r"let\s+ans(?:\s*:\s*f64)?\s*=\s*(.+?);", expr)
        if not m:
            return BuildLangExecResult(False, None, "", "offline_missing_ans_binding", "sandbox_ast_f64")
        expr = m.group(1)
    try:
        tree = ast.parse(expr, mode="eval")
        val = _eval_ast_node(tree)
    except Exception as exc:
        return BuildLangExecResult(False, None, "", f"ast_f64_error: {exc}", "sandbox_ast_f64")
    if not math.isfinite(val):
        return BuildLangExecResult(False, None, "", "non_finite_f64", "sandbox_ast_f64")
    return BuildLangExecResult(True, val, repr(val), "", "sandbox_ast_f64")


def build_fca_recall_header(task: EvalTask) -> str:
    """Factorized Context Attention (FCA) block-compressed recall header (<= 125 tokens)."""
    if task.domain == "DS-03":
        return (
            f"[FCA:SPEC] {task.recall_card}\n"
            "[FCA:TOOL] Never compute floats mentally. Emit ONE line calling the BuildLang "
            "f64 compiler tool: `BUILDLANG_F64: <expr>` using float literals (e.g. 1.0, 2.0) "
            "and builtins `pow(a, b)`, `exp(x)`, `sqrt(x)`, `+`, `-`, `*`, `/`."
        )
    if task.domain == "DS-02":
        return (
            f"[FCA:SYNTAX] {task.recall_card}\n"
            "[FCA:TOOL] Emit clean BuildLang inside ```bld```; live verified via buildc check + run."
        )
    return (
        f"[FCA:SPEC] {task.recall_card}\n"
        "[FCA:TOOL] Allowed TOOL names are strictly `Bash`, `Glob`, `Grep`, `Read`. "
        "CLI commands (buildc, git, pytest) MUST use `TOOL: Bash`."
    )


def extract_buildlang_tool_call(response: str) -> str | None:
    """Extract BUILDLANG_F64 expression or fenced BuildLang block from model reply."""
    m = _BLD_F64_RE.search(response)
    if m:
        expr = m.group(1).strip().strip("`").strip()
        if expr:
            return expr
    fm = _FENCE_RE.search(response)
    if fm and ("fn main" in fm.group(1) or "pow(" in fm.group(1) or "exp(" in fm.group(1)):
        return fm.group(1).strip()
    return None


def format_arm_c_prompt(task: EvalTask) -> str:
    """Build non-contradictory FCA + BuildLang tool-calling prompt for Arm C."""
    header = build_fca_recall_header(task)
    body = task.prompt
    if task.domain == "DS-03":
        body = body.split("Reply with a single final line")[0].strip()
        body += " Reply ONLY with one line: `BUILDLANG_F64: <valid BuildLang f64 expression>`."
    return f"{header}\n\nTask:\n{body}"


def evaluate_arm_c_attempt(
    task: EvalTask, response: str, *, use_live_buildc: bool
) -> tuple[bool, str, bool]:
    """Verify Arm C response, requiring live BuildLang f64 tool execution on DS-03."""
    if task.domain == "DS-03":
        expr = extract_buildlang_tool_call(response)
        if expr is None:
            return False, "tool_not_called: reply with `BUILDLANG_F64: <expr>` (no mental math)", False
        res = exec_buildlang_f64(expr, use_live_buildc=use_live_buildc)
        if not res.ok or res.value is None:
            return False, f"buildlang_tool_error: {res.error}", True
        ok, diag = verify_task_output(task, f"ANSWER: {res.value:.15g}", use_live_buildc=use_live_buildc)
        return ok, (f"MATCH({res.mode})" if ok else f"{diag} [buildc_val={res.value:.6g}]"), True
    ok, diag = verify_task_output(task, response, use_live_buildc=use_live_buildc)
    return ok, diag, False
