"""diff_mutation.py -- the diff-scoped mode of the suite audit (check B3).

suite_audit.py asks whether a whole suite can refuse wrong code. This asks the
narrower question a reviewer has about one change: for the lines this change
added or edited, which one-operator mutants do the tests let through? It
mutates only changed non-test lines (one mutant per line, operator drawn at
random with a recorded seed, arid lines skipped), runs only the tests whose
coverage reaches each mutated line, and reports each survivor by file, line,
original and mutant.

There is deliberately no score. A kill rate as a target teaches change-detector
tests; survivors are review prompts, and a reviewer can dismiss one as an
equivalent mutant. Mutation happens in a scratch copy of the head commit, never
in the caller's checkout. Standard library only; coverage.py is used through a
subprocess when the target Python has it, and without it every selected test
runs for every mutant (recorded as `selection: all-selected`).
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

from .line_mutants import mutants_for_lines
from .red_check import _changed, _env, _git, materialize, run_tests
from .red_classify import is_test_path, parse_junit
from .red_select import changed_tests

SCHEMA = "flywheel.suite-audit-diff/v1"
DOES_NOT_PROVE = (
    "A killed mutant shows a test can detect that change, not that the test checks "
    "the requirement the author meant.",
    "A survivor can be an equivalent mutant that no test could kill; it is a prompt "
    "for review, not a verdict.",
    "Mutants stand in for real faults imperfectly: Just et al. (2014) found 27% of "
    "real faults not coupled to common mutants.",
    "Only changed lines are mutated, one operator per line, so most possible faults "
    "in the change are never tried.",
    "Python only. Other languages are not mutated and are not reported clean.",
)
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(repo, base, head, path) -> set:
    out = set()
    diff = _git(repo, "diff", "-U0", "--no-color", base, head, "--", path)
    for line in diff.splitlines():
        match = _HUNK.match(line)
        if match:
            start, count = int(match.group(1)), int(match.group(2) or 1)
            out.update(range(start, start + count))
    return out


def _selected_tests(repo, base, head, changed, tree: Path, tests) -> list:
    if tests:
        return list(tests)
    nodes = []
    for status, path in changed:
        name = PurePosixPath(path).name
        if status != "D" and path.endswith(".py") and name.startswith("test_"):
            before = "" if status == "A" else _git(repo, "show", f"{base}:{path}")
            nodes += [n.split("::")[0] for n in changed_tests(path, before,
                                                             _git(repo, "show", f"{head}:{path}"))]
    return sorted(set(nodes))


def _coverage(tree: Path, nodes, timeout, python) -> "tuple | None":
    """(junit dict, {relpath: {line: [context]}}) from one coverage run, or None
    when coverage.py is not importable in the target Python."""
    probe = subprocess.run([python, "-c", "import coverage"], capture_output=True, check=False)
    if probe.returncode != 0:
        return None
    rc = tree / ".red-check-coveragerc"
    rc.write_text("[run]\ndynamic_context = test_function\nbranch = False\n"
                  f"data_file = {tree / '.red-check-coverage'}\n", encoding="utf-8")
    junit = tree / ".red-check-junit.xml"
    argv = [python, "-m", "coverage", "run", f"--rcfile={rc}", "-m", "pytest", *nodes,
            "-p", "no:cacheprovider", "--continue-on-collection-errors",
            f"--junitxml={junit}", "-q"]
    out_json = tree / ".red-check-coverage.json"
    try:
        subprocess.run(argv, cwd=str(tree), env=_env(tree), capture_output=True,
                       timeout=timeout * 2, check=False)
        subprocess.run([python, "-m", "coverage", "json", f"--rcfile={rc}", "--show-contexts",
                        "-o", str(out_json)], cwd=str(tree), env=_env(tree),
                       capture_output=True, timeout=300, check=False)
    except subprocess.TimeoutExpired:
        return None   # the caller falls back to running every selected test
    contexts = {}
    if out_json.is_file():
        data = json.loads(out_json.read_text(encoding="utf-8"))
        root = str(tree.resolve())
        for fname, info in data.get("files", {}).items():
            path = Path(fname)   # coverage writes paths relative to the run folder
            rel = str(path.resolve()).replace(root, "") if path.is_absolute() else fname
            rel = rel.lstrip("\\/").replace("\\", "/")
            contexts[rel] = info.get("contexts", {})
    xml = junit.read_text(encoding="utf-8", errors="replace") if junit.is_file() else ""
    return {"xml": xml}, contexts


def _context_nodes(contexts: list, nodes: list) -> list:
    """Map coverage contexts like 'test_mod.Class.test_fn' to node ids."""
    out = set()
    for ctx in contexts:
        if not ctx:
            continue
        parts = ctx.split(".")
        for node in nodes:
            stem = PurePosixPath(node.split("::")[0]).stem
            if parts[0] == stem:
                out.add(node.split("::")[0] + "::" + "::".join(parts[1:]))
    return sorted(out)


def _failed(run) -> "bool | None":
    if run is None or not run.get("xml"):
        return None
    rows = [r for rs in parse_junit(run["xml"], set()).values() for r in rs]
    if not rows:
        return None
    if any(c not in ("green", "skipped") for c, _ in rows):
        return True
    return False if any(c == "green" for c, _ in rows) else None


def _baseline_failures(run) -> set:
    """Test names (Class::fn or fn) that fail or error unmutated."""
    if not run or not run.get("xml"):
        return set()
    out = set()
    for (classname, name), rows in parse_junit(run["xml"], set()).items():
        if any(c not in ("green", "skipped") for c, _ in rows):
            out.add(name if "." not in classname or not classname.split(".")[-1][:1].isupper()
                    else classname.split(".")[-1] + "::" + name)
    return out


def _plan(repo, base, head, changed, tree, rng, max_mutants) -> tuple:
    planned = []
    for status, path in changed:
        if status == "D" or not path.endswith(".py") or is_test_path(path):
            continue
        lines = changed_lines(repo, base, head, path)
        source = (tree / path).read_text(encoding="utf-8", errors="replace")
        planned += mutants_for_lines(path, source, lines, rng)
    rng.shuffle(planned)
    return planned[:max_mutants], max(0, len(planned) - max_mutants)


def audit_diff(repo, base, head, tests=None, *, max_mutants: int = 30,
               budget_seconds: int = 600, timeout: int = 120, seed=None,
               python=sys.executable, workdir=None, overlay=None) -> dict:
    """Survivors among one-per-line mutants of a change's non-test lines.
    `overlay` maps repository paths to replacement test text for the run."""
    t0, repo = time.time(), Path(repo)
    base = _git(repo, "rev-parse", "--verify", base + "^{commit}").strip()
    head = _git(repo, "rev-parse", "--verify", head + "^{commit}").strip()
    seed = random.SystemRandom().randrange(2 ** 32) if seed is None else seed
    rng = random.Random(seed)
    changed = _changed(repo, base, head)
    receipt = {"schema": SCHEMA, "mode": "report-only", "repo": repo.name, "base": base,
               "head": head, "seed": seed, "max_mutants": max_mutants,
               "budget_seconds": budget_seconds, "survivors": [], "not_covered": [],
               "indeterminate": [], "does_not_prove": list(DOES_NOT_PROVE)}
    with tempfile.TemporaryDirectory(prefix="diff-mutation-", dir=workdir,
                                     ignore_cleanup_errors=True) as tmp:
        tree = Path(tmp) / "head"
        materialize(repo, head, tree)
        for rel, text in (overlay or {}).items():   # a replacement test, as in red_check
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_text(text, encoding="utf-8", newline="")
        nodes = _selected_tests(repo, base, head, changed, tree, tests)
        planned, dropped = _plan(repo, base, head, changed, tree, rng, max_mutants)
        receipt.update(tests=nodes, planned=len(planned), over_cap=dropped)
        if not nodes or not planned:
            receipt.update(status="nothing-to-run" if planned else "no-mutable-lines",
                           run=0, killed=0, wall_seconds=round(time.time() - t0, 1))
            return receipt
        cov = _coverage(tree, nodes, timeout, python)
        baseline = cov[0] if cov else run_tests(tree, nodes, timeout, python)
        broken = _baseline_failures(baseline)
        receipt["selection"] = "coverage" if cov else "all-selected"
        receipt["baseline_failing"] = sorted(broken)
        if _failed(baseline) is None:
            receipt.update(status="broken-reference", run=0, killed=0,
                           wall_seconds=round(time.time() - t0, 1))
            return receipt
        run = killed = 0
        for mutant in planned:
            if time.time() - t0 > budget_seconds:
                break
            row = {"file": mutant.path, "line": mutant.line, "operator": mutant.operator,
                   "original": mutant.original[:200], "mutant": mutant.mutated[:200]}
            covering = (_context_nodes(cov[1].get(mutant.path, {}).get(str(mutant.line), []),
                                       nodes) if cov else list(nodes))
            covering = [n for n in covering if n.split("::", 1)[-1] not in broken]
            if not covering:
                receipt["not_covered"].append(row)
                continue
            target = tree / mutant.path
            original = target.read_bytes()
            try:
                target.write_text(mutant.source, encoding="utf-8", newline="")
                first = _failed(run_tests(tree, covering, timeout, python))
                outcome = first
                if first is True:     # a kill disagrees with the baseline: confirm it
                    outcome = True if _failed(run_tests(tree, covering, timeout, python)) \
                        else None
            finally:
                target.write_bytes(original)
            run += 1
            row["tests"] = covering[:10]
            if outcome is True:
                killed += 1
            elif outcome is False:
                receipt["survivors"].append(row)
            else:
                receipt["indeterminate"].append(row)
        skipped = len(planned) - run - len(receipt["not_covered"])
        receipt.update(status="partial" if skipped else "complete", run=run, killed=killed,
                       skipped_for_budget=skipped, wall_seconds=round(time.time() - t0, 1))
    return receipt
