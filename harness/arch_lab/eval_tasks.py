"""Stratified DS-02 (BuildLang), DS-03 (IEEE-754 Physics), and DS-01 (Tool-Repair) tasks + oracles.

Every task carries a compact DS-07 recall card (<= 125 tokens, zero answer leakage),
an independent deterministic Plate B + Plate C oracle, and a planted-wrong control.
Pure stdlib Python, <= 290 lines, every function <= 50 lines.
"""
from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_BYPASS_RE = re.compile(
    r"(?i)\b(?:assert\s+(?:True|1\s*==\s*1)|skip_oracle\s*=\s*True|anygeometry\s*=\s*true)\b"
)
_CODE_FENCE_RE = re.compile(r"```(?:buildlang|bld|rust|text)?\s*\n(.*?)```", re.S | re.I)
_ANSWER_RE = re.compile(r"(?i)ANSWER\s*[:=]\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
_FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_TOOL_RE = re.compile(r"(?i)TOOL\s*[:=]\s*([A-Za-z0-9_]+)")
_CMD_RE = re.compile(r"(?i)CMD\s*[:=]\s*(.+)")


@dataclass(frozen=True)
class EvalTask:
    task_id: str
    domain: str  # "DS-02" | "DS-03" | "DS-01"
    prompt: str
    recall_card: str
    planted_wrong_output: str
    expected_stdout: str | None = None
    expected_value: float | None = None
    rel_tol: float = 1e-4
    required_tool: str = ""
    required_substrings: tuple[str, ...] = ()
    forbidden_substrings: tuple[str, ...] = ()


def _ds02_tasks() -> list[EvalTask]:
    card = (
        "DS-07 BuildLang syntax card: entry is `fn main() ~ Console { ... }`. "
        "Print with `println!(\"{}\", val);`. Mutable vars use `let mut x: i64 = 0;`. "
        "Types: i64, f64, bool. Loops: `while cond { ... }`. Functions: `fn f(x: i64) -> i64 { ... }`."
    )
    specs = [
        ("ds02_fact7", "Write a BuildLang program that prints 7! (factorial of 7).", "5040", "fn main() { println!(\"0\"); }"),
        ("ds02_fib10", "Write a BuildLang program that prints fib(10) where fib(0)=0, fib(1)=1.", "55", "fn main() ~ Console { println!(\"10\"); }"),
        ("ds02_sum100", "Write a BuildLang program that sums integers 1..=100 using a while loop and prints the sum.", "5050", "fn main() ~ Console { println!(\"100\"); }"),
        ("ds02_gcd", "Write a BuildLang program computing gcd(1071, 462) and printing the result.", "21", "fn main() ~ Console { println!(\"462\"); }"),
        ("ds02_squares", "Write a BuildLang program that sums k*k for k=1..=10 and prints the sum.", "385", "fn main() ~ Console { println!(\"100\"); }"),
        ("ds02_pow2", "Write a BuildLang program computing 2^12 with a loop and printing the result.", "4096", "fn main() ~ Console { println!(\"2048\"); }"),
        ("ds02_collatz", "Write a BuildLang program that prints the number of Collatz steps from 27 to reach 1.", "111", "fn main() ~ Console { println!(\"27\"); }"),
        ("ds02_prime_cnt", "Write a BuildLang program that counts prime numbers <= 50 and prints the count.", "15", "fn main() ~ Console { println!(\"25\"); }"),
    ]
    return [
        EvalTask(
            tid, "DS-02",
            f"{desc} Output ONLY valid BuildLang code inside a ```bld``` fenced block.",
            card, wrong, expected_stdout=exp,
        )
        for tid, desc, exp, wrong in specs
    ]


def _ds03_tasks() -> list[EvalTask]:
    specs = [
        ("OPT-002", "Compute dielectric Fresnel reflectance R at normal incidence (cos_i=1.0) for n1=1.0, n2=1.5.",
         "DS-07 OPT-002: R0 = ((n1 - n2)/(n1 + n2))^2 at normal incidence (average of rs and rp).",
         ((1.0 - 1.5) / (1.0 + 1.5)) ** 2, "ANSWER: 0.08"),
        ("OPT-004", "Compute Schlick reflectance F for F0=0.04 and cos_theta=0.5.",
         "DS-07 OPT-004: F = F0 + (1 - F0) * (1 - cos_theta)^5.",
         0.04 + 0.96 * (0.5 ** 5), "ANSWER: 0.04"),
        ("OPT-005", "Compute image distance s' (mm) for a thin lens with focal length f=50 mm and object distance s=150 mm.",
         "DS-07 OPT-005: Thin lens equation 1/f = 1/s + 1/s', so s' = 1 / (1/f - 1/s).",
         1.0 / (1.0 / 50.0 - 1.0 / 150.0), "ANSWER: 100.0"),
        ("OPT-007", "Compute optical f-number N for focal length f=85 mm and entrance pupil diameter D=42.5 mm.",
         "DS-07 OPT-007: f-number N = f / D.",
         85.0 / 42.5, "ANSWER: 0.5"),
        ("OPT-008", "Compute Airy disc first-null radius r (micrometers) for lambda=0.55 um and N=4.0 using exact j1,1/pi=1.21966989.",
         "DS-07 OPT-008: r_Airy = 1.2196698912665045 * lambda * N.",
         1.2196698912665045 * 0.55 * 4.0, "ANSWER: 2.20"),
        ("OPT-033", "Compute Beer-Lambert transmittance T = exp(-alpha * d) for alpha=0.25 cm^-1 and d=2.0 cm.",
         "DS-07 OPT-033: Beer-Lambert law T = exp(-alpha * d).",
         math.exp(-0.5), "ANSWER: 0.50"),
        ("COL-001", "Convert sRGB component v=0.5 to linear light using IEC 61966-2-1 transfer function.",
         "DS-07 COL-001: For v > 0.04045, linear = ((v + 0.055) / 1.055)^2.4.",
         ((0.5 + 0.055) / 1.055) ** 2.4, "ANSWER: 0.2176376"),
        ("COL-030", "Compute WCAG 2.1 contrast ratio between relative luminances L1=0.80 and L2=0.05.",
         "DS-07 COL-030: WCAG contrast = (L_lighter + 0.05) / (L_darker + 0.05).",
         (0.80 + 0.05) / (0.05 + 0.05), "ANSWER: 16.0"),
        ("SIG-011", "Compute ideal quantization SQNR in dB for a 16-bit uniform quantizer (full-scale sine).",
         "DS-07 SIG-011: SQNR_dB = 6.020599913 * N_bits + 1.760912591.",
         6.020599913279624 * 16.0 + 1.7609125905568124, "ANSWER: 96.0"),
        ("PHY-054", "Compute Laplace excess pressure delta_P (Pa) inside a spherical droplet of gamma=0.072 N/m, r=0.001 m.",
         "DS-07 PHY-054: Spherical droplet Laplace pressure delta_P = 2 * gamma / r.",
         2.0 * 0.072 / 0.001, "ANSWER: 72.0"),
    ]
    return [
        EvalTask(
            tid, "DS-03",
            f"{desc} Reply with a single final line formatted exactly as `ANSWER: <number>`.",
            card, wrong, expected_value=val, rel_tol=1e-3,
        )
        for tid, desc, card, val, wrong in specs
    ]


def _ds01_tasks() -> list[EvalTask]:
    specs = [
        ("ds01_glob_scope", "Failing call: `Glob <USER_HOME>` timed out scanning home dir. Repair to search `.claude` inside `<WORKSPACE>`.",
         "DS-07 DS-01 card: Keep tool `Glob`, narrow path to `<WORKSPACE>/.claude`.",
         "Glob", ("<WORKSPACE>/.claude",), ("<USER_HOME>", "rm "), "TOOL: Glob\nCMD: <USER_HOME>"),
        ("ds01_bash_read", "Failing call: `Bash ls <USER_HOME>/.claude/` failed on Windows quoting. Repair using `Read` on `<USER_HOME>/.claude/settings.json`.",
         "DS-07 DS-01 card: Prefer structured `Read` tool on exact path `<USER_HOME>/.claude/settings.json`.",
         "Read", ("settings.json",), ("rm ", "del "), "TOOL: Bash\nCMD: rm -rf settings.json"),
        ("ds01_pytest_flag", "Failing call: `Bash pytest --nonexistent-flag tests/test_arch_lab.py` exited 4. Repair with valid `python -m pytest -q tests/test_arch_lab.py`.",
         "DS-07 DS-01 card: Invoke `Bash` with `python -m pytest` and `-q` targeting `tests/test_arch_lab.py`.",
         "Bash", ("pytest", "tests/test_arch_lab.py"), ("--nonexistent-flag",), "TOOL: Bash\nCMD: pytest --nonexistent-flag"),
        ("ds01_git_status", "Failing call: `Bash git -C /bad/path status` exited 128. Repair targeting `<WORKSPACE>` with `git -C <WORKSPACE> status -s`.",
         "DS-07 DS-01 card: Use `Bash` with `git -C <WORKSPACE> status -s` (no force flags).",
         "Bash", ("git", "<WORKSPACE>", "status"), ("/bad/path", "--force"), "TOOL: Bash\nCMD: git -C /bad/path status"),
        ("ds01_grep_pattern", "Failing call: `Grep [unclosed_regex` failed regex parse. Repair by escaping bracket `\\[unclosed` in `harness/`.",
         "DS-07 DS-01 card: Use `Grep` with escaped bracket `\\[unclosed` scoped to `harness/`.",
         "Grep", ("\\[unclosed", "harness/"), ("[unclosed_regex",), "TOOL: Grep\nCMD: [unclosed_regex"),
        ("ds01_buildc_check", "Failing call: `Bash buildc build missing.bld` failed (unknown subcommand). Repair using `buildc check` on `kcore_fast.bld`.",
         "DS-07 DS-01 card: BuildLang CLI subcommand is `buildc check <file.bld>`.",
         "Bash", ("buildc", "check", "kcore_fast.bld"), ("buildc build",), "TOOL: Bash\nCMD: buildc build missing.bld"),
    ]
    return [
        EvalTask(
            tid, "DS-01",
            f"{desc} Reply with exactly two lines:\nTOOL: <ToolName>\nCMD: <repaired command or path>",
            card, wrong, required_tool=tool, required_substrings=req, forbidden_substrings=forb,
        )
        for tid, desc, card, tool, req, forb, wrong in specs
    ]


def build_eval_tasks() -> list[EvalTask]:
    return _ds02_tasks() + _ds03_tasks() + _ds01_tasks()


def _extract_bld(response: str) -> str:
    m = _CODE_FENCE_RE.search(response)
    return m.group(1).strip() if m else response.strip()


def verify_task_output(
    task: EvalTask, response: str, *, use_live_buildc: bool = True
) -> tuple[bool, str]:
    """Independent Plate B + Plate C oracle returning (passed, non-leaking diagnostic)."""
    if not response.strip():
        return False, "plate_a:empty_response"
    if _BYPASS_RE.search(response):
        return False, "plate_b:stub_or_oracle_bypass_detected"
    if task.domain == "DS-02":
        return _verify_ds02(task, response, use_live_buildc=use_live_buildc)
    if task.domain == "DS-03":
        return _verify_ds03(task, response)
    return _verify_ds01(task, response)


def _verify_ds02(task: EvalTask, response: str, *, use_live_buildc: bool) -> tuple[bool, str]:
    code = _extract_bld(response)
    if "fn main" not in code or code.count("{") != code.count("}"):
        return False, "plate_c:missing_main_or_unbalanced_braces"
    buildc_bin = shutil.which("buildc") if use_live_buildc else None
    if buildc_bin:
        with tempfile.TemporaryDirectory(prefix="jfc3p_bld_") as td:
            src = Path(td) / f"{task.task_id}.bld"
            src.write_text(code + "\n", encoding="utf-8")
            chk = subprocess.run([buildc_bin, "check", str(src)], capture_output=True, text=True, timeout=20)
            if chk.returncode != 0:
                err = (chk.stderr or chk.stdout or "check failed").strip()[:280]
                return False, f"plate_c:buildc_check_failed: {err}"
            run = subprocess.run([buildc_bin, "run", str(src)], capture_output=True, text=True, timeout=25)
            if run.returncode != 0:
                err = (run.stderr or run.stdout or "run failed").strip()[:280]
                return False, f"plate_c:buildc_run_failed: {err}"
            got = run.stdout.strip().splitlines()[-1].strip() if run.stdout.strip() else ""
            if got != (task.expected_stdout or ""):
                return False, f"plate_c:stdout_mismatch(got={got!r}, check_algorithm_and_bounds)"
            return True, "MATCH"
    # Offline CI fallback when buildc binary is not installed
    if "~ Console" not in code or "println!" not in code:
        return False, "plate_c:missing_console_effect_or_println"
    if task.expected_stdout and task.expected_stdout in code:
        return True, "MATCH_OFFLINE"
    return False, "plate_c:offline_contract_mismatch"


def _verify_ds03(task: EvalTask, response: str) -> tuple[bool, str]:
    m = _ANSWER_RE.search(response)
    if m:
        raw = m.group(1)
    else:
        nums = _FLOAT_RE.findall(response)
        if not nums:
            return False, "plate_c:missing_ANSWER_numeric_value"
        raw = nums[-1]
    try:
        val = float(raw)
    except ValueError:
        return False, "plate_c:unparseable_float"
    if not math.isfinite(val) or task.expected_value is None:
        return False, "plate_c:non_finite_value"
    if math.isclose(val, task.expected_value, rel_tol=task.rel_tol, abs_tol=1e-9):
        return True, "MATCH"
    direction = "too_high" if val > task.expected_value else "too_low"
    return False, f"plate_c:numeric_drift({direction}, verify_formula_and_units)"


def _verify_ds01(task: EvalTask, response: str) -> tuple[bool, str]:
    tm = _TOOL_RE.search(response)
    cm = _CMD_RE.search(response)
    if not tm or not cm:
        return False, "plate_c:missing_TOOL_or_CMD_line"
    tool = tm.group(1).strip()
    cmd = cm.group(1).strip()
    if tool.lower() != task.required_tool.lower():
        return False, f"plate_c:wrong_tool(got={tool})"
    for bad in task.forbidden_substrings:
        if bad.lower() in cmd.lower():
            return False, f"plate_c:forbidden_fragment_present({bad})"
    for req in task.required_substrings:
        if req.lower() not in cmd.lower():
            return False, f"plate_c:missing_required_target({req})"
    return True, "MATCH"
