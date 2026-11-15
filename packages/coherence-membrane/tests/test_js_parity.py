"""Cross-implementation parity: the JS reference core re-derives the same corpus.

This is what turns re-derivability from *demonstrable* into *demonstrated* -- a
second, independent implementation (impl/js/, sharing no code with the Python
reference) re-derives every frozen value in conformance/vectors.json. The Python
suite runs the JS harness as a subprocess so the proof is checked here too.
Skips cleanly if Node is not installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_js_reference_core_re_derives_the_corpus():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, str(REPO / "impl" / "js" / "run.js")],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["impl"] == "js"
    assert summary["failed"] == 0
    assert summary["passed"] == summary["cases"]
    assert summary["cases"] >= 15  # fixed floor: corpus must not silently shrink
    # the JS impl must cover exactly the cases the Python corpus pins
    vectors = json.loads((REPO / "conformance" / "vectors.json").read_text("utf-8"))
    assert summary["cases"] == len(vectors["cases"])


def test_js_and_python_harnesses_agree_case_for_case():
    """Strongest form: for every case, the JS result equals the Python result
    (not just 'both pass') -- the two implementations agree value-for-value."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    # JS: emit each case's re-derived result as JSON
    driver = (
        "const M=require('./impl/js/run.js');"
        "const fs=require('fs');"
        "const v=JSON.parse(fs.readFileSync('conformance/vectors.json','utf8'));"
        "const out=v.cases.map(c=>({id:c.id,got:M.runCase(c)}));"
        "process.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run([node, "-e", driver], capture_output=True, text=True, cwd=str(REPO))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    js_results = {r["id"]: r["got"] for r in json.loads(proc.stdout)}

    import sys
    sys.path.insert(0, str(REPO / "conformance"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("cm_run", REPO / "conformance" / "run.py")
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)

    vectors = json.loads((REPO / "conformance" / "vectors.json").read_text("utf-8"))
    assert len(js_results) >= 15  # fixed floor: corpus must not silently shrink
    for case in vectors["cases"]:
        py = run.run_case(case)
        js = js_results[case["id"]]
        assert js == py, f"{case['id']}: js={js!r} != py={py!r}"
