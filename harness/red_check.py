"""red_check.py -- do a change's new tests fail on the code before the change?

For a bug fix, a test written against the fixed code only shows it encodes the
expected behaviour if it fails on the old code, and fails for the right reason.
This check copies the parent commit into a scratch folder, lays the head
commit's new and changed test files over it, runs only the new and changed
tests, and sorts each one with red_classify: red-assert, red-missing-symbol,
red-error, skipped, green, or indeterminate.

Three controls keep a red from being credited by accident:
  * the same tests must pass at the head commit, or the red says nothing;
  * the base run happens twice, and disagreement is indeterminate (flaky);
  * the scratch tree's own packages must be what Python imports, or every
    result is indeterminate (an installed copy would be tested instead).

Report-only. It runs code from the repository, so call it on code you would
run anyway. Standard library only.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from .red_classify import (defined_names, is_test_path, module_names, outcome_for,
                           parse_junit)
from .red_select import changed_tests

SCHEMA = "flywheel.red-check/v1"
DOES_NOT_PROVE = (
    "A red-assert result shows the test failed on the old code on an assertion, not "
    "that it fails for the reason the author claims.",
    "red-missing-symbol is never credited: it shows the API is new, not that the test "
    "checks behaviour. Mutation (survivors) is the evidence for features.",
    "Only new and changed test functions run. A weakened older test that still "
    "passes is the static test-diff check's job.",
    "Two base runs separate stable from flaky results only as far as two samples can.",
    "Python and pytest only. Other languages are not run and are not reported clean.",
)


def _git(repo, *args, data=False):
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: "
                           + proc.stderr.decode("utf-8", "replace").strip()[:300])
    return proc.stdout if data else proc.stdout.decode("utf-8", "replace")


def materialize(repo, ref, dest: Path) -> None:
    """Write the tree of `ref` into dest with git archive (no checkout, no
    change to the repository's branches or worktrees)."""
    blob = _git(repo, "archive", "--format=tar", ref, data=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:  # pragma: no cover -- Python without extraction filters
            tar.extractall(dest)


def _changed(repo, base, head) -> list:
    out = []
    rows = _git(repo, "diff", "--name-status", "--no-renames", base, head).splitlines()
    for row in rows:
        status, _, path = row.partition("\t")
        out.append((status[:1], path))
    return out


def _new_names(repo, base, head, changed) -> set:
    names: set = set()
    for status, path in changed:
        if not path.endswith(".py") or is_test_path(path):
            continue
        after = "" if status == "D" else _git(repo, "show", f"{head}:{path}")
        before = "" if status == "A" else _git(repo, "show", f"{base}:{path}")
        names |= defined_names(after) - defined_names(before)
        if status == "A":
            names |= module_names(path)
    return names


def _packages(tree: Path) -> list:
    out = []
    for root in (tree, tree / "src"):
        if root.is_dir():
            out += [p.name for p in root.iterdir()
                    if p.is_dir() and (p / "__init__.py").is_file() and p.name.isidentifier()
                    and not is_test_path(p.name + "/x.py")]
    return sorted(set(out))


def _env(tree: Path) -> dict:
    from .oracle import run_env
    paths = [str(tree), str(tree / "src")]
    return run_env({"PYTHONPATH": os.pathsep.join(paths)}, cwd=tree)


def provenance(tree: Path, python=sys.executable) -> dict:
    """Where Python finds each top-level package of the scratch tree. Any origin
    outside the tree means an installed copy would be tested: drift."""
    packages = _packages(tree)
    if not packages:
        return {"status": "ok", "packages": {}}
    code = ("import importlib.util,json,sys\nout={}\nfor n in sys.argv[1:]:\n"
            "    try:\n        s=importlib.util.find_spec(n)\n"
            "        out[n]=(s.origin or (list(s.submodule_search_locations or [''])[0]))"
            " if s else None\n    except Exception as e:\n        out[n]='error: '+str(e)\n"
            "print(json.dumps(out))")
    proc = subprocess.run([python, "-c", code, *packages], cwd=str(tree), env=_env(tree),
                          capture_output=True, text=True, timeout=60, check=False)
    try:
        found = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"status": "drift", "packages": {}, "outside": {"<probe>": proc.stderr[-300:]}}
    root = str(tree.resolve()).lower()
    outside = {n: o for n, o in found.items()
               if not o or not str(Path(o).resolve()).lower().startswith(root)}
    return {"status": "drift" if outside else "ok", "packages": found,
            "outside": outside}


def run_tests(tree: Path, node_ids: list, timeout: int, python=sys.executable) -> "dict | None":
    """One pytest run of node_ids in tree. Returns the parsed JUnit report, or
    None on a timeout (a hang is not a verdict)."""
    from .proc_kill import _kill_tree, spawn_killable
    junit = tree / ".red-check-junit.xml"
    junit.unlink(missing_ok=True)
    for cache in tree.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    argv = [python, "-m", "pytest", *node_ids, "-p", "no:cacheprovider",
            "--continue-on-collection-errors", f"--junitxml={junit}", "-q"]
    proc = spawn_killable(argv, cwd=str(tree), env=_env(tree),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=10)
        except Exception:  # noqa: BLE001 -- the drain after a kill is best effort
            pass
        return None
    if not junit.is_file():
        return {}
    return {"xml": junit.read_text(encoding="utf-8", errors="replace")}


def _overlay(repo, head, tree: Path, changed, overlay) -> list:
    written = []
    for status, path in changed:
        if is_test_path(path) and status != "D":
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_git(repo, "show", f"{head}:{path}", data=True))
            written.append(path)
    for path, text in (overlay or {}).items():
        target = tree / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="")
        written.append(path)
    return sorted(set(written))


def _select(repo, base, head, changed, tests) -> list:
    if tests:
        return list(tests)
    out = []
    for status, path in changed:
        name = path.rsplit("/", 1)[-1]
        if status == "D" or not path.endswith(".py") or not (
                name.startswith("test_") or name.endswith("_test.py")):
            continue
        before = "" if status == "A" else _git(repo, "show", f"{base}:{path}")
        out += changed_tests(path, before, _git(repo, "show", f"{head}:{path}"))
    return out


def _sha(value) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fold(node, base_runs, head_run, new_names, prov) -> dict:
    row = {"test": node}
    outcomes = []
    for run in base_runs:
        if run is None:
            outcomes.append(("indeterminate", "the base run timed out"))
        elif not run.get("xml"):
            outcomes.append(("indeterminate", "the base run wrote no report"))
        else:
            outcomes.append(outcome_for(node, parse_junit(run["xml"], new_names)))
    classes = sorted({c for c, _ in outcomes})
    cls, detail = outcomes[0]
    if len(classes) > 1:
        cls, detail = "indeterminate", "flaky: base runs disagree (" + ", ".join(classes) + ")"
    row["base_runs"] = [c for c, _ in outcomes]
    if head_run is not None:
        head_cls = (outcome_for(node, parse_junit(head_run["xml"], set()))[0]
                    if head_run.get("xml") else "no-report")
        row["head"] = "pass" if head_cls == "green" else head_cls
        if head_cls != "green" and cls != "indeterminate":
            cls, detail = "indeterminate", f"does not pass at head ({head_cls}): {detail}"
    elif head_run is None and base_runs:
        row["head"] = "not-run"
    if prov["status"] != "ok" and cls != "indeterminate":
        cls, detail = "indeterminate", "an installed copy shadows the scratch tree: " + detail
    row["class"], row["detail"] = cls, detail[:300]
    return row


def red_check(repo, base, head, tests=None, *, overlay=None, runs: int = 2,
              timeout: int = 300, check_head: bool = True, python=sys.executable,
              workdir=None) -> dict:
    """Run the red check for one change. Returns the receipt (a dict)."""
    t0, repo = time.time(), Path(repo)
    base = _git(repo, "rev-parse", "--verify", base + "^{commit}").strip()
    head = _git(repo, "rev-parse", "--verify", head + "^{commit}").strip()
    changed = _changed(repo, base, head)
    nodes = _select(repo, base, head, changed, tests)
    receipt = {"schema": SCHEMA, "mode": "report-only", "repo": repo.name, "base": base,
               "head": head, "tests": [], "counts": {}, "credited": 0,
               "does_not_prove": list(DOES_NOT_PROVE)}
    receipt["subject_sha256"] = _sha([base, head, sorted(nodes), overlay or {}])
    if not nodes:
        receipt.update(status="no-tests", claim_sha256=_sha([]),
                       wall_seconds=round(time.time() - t0, 1))
        return receipt
    new_names = _new_names(repo, base, head, changed)
    with tempfile.TemporaryDirectory(prefix="red-check-", dir=workdir,
                                     ignore_cleanup_errors=True) as tmp:
        base_tree = Path(tmp) / "base"
        materialize(repo, base, base_tree)
        receipt["overlaid"] = _overlay(repo, head, base_tree, changed, overlay)
        prov = provenance(base_tree, python)
        base_runs = [run_tests(base_tree, nodes, timeout, python) for _ in range(max(1, runs))]
        head_run = None
        if check_head:
            head_tree = Path(tmp) / "head"
            materialize(repo, head, head_tree)
            _overlay(repo, head, head_tree, [], overlay)
            head_run = run_tests(head_tree, nodes, timeout, python) or {}
    rows = [_fold(n, base_runs, head_run, new_names, prov) for n in nodes]
    counts: dict = {}
    for row in rows:
        counts[row["class"]] = counts.get(row["class"], 0) + 1
    receipt.update(status="ran", tests=rows, counts=counts,
                   credited=counts.get("red-assert", 0), provenance=prov,
                   claim_sha256=_sha(rows), wall_seconds=round(time.time() - t0, 1))
    return receipt
