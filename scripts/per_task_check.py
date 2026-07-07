"""Per-task single-shot (greedy) pass/fail on the hard set against the live serve,
so the aggregate 80->90 lift is grounded in exactly which tasks greedy fails."""
import sys
from pathlib import Path
sys.path.insert(0, "/mnt/c/dev/local-model")

from harness.tasks_hard import HARD_REGISTRY
from harness.tasks_lib import materialize_all
from harness.task import load_task
from harness.proposer import ServeProposer
from harness.oracle import PytestOracle

p = ServeProposer("http://127.0.0.1:8765")
oracle = PytestOracle()
root = Path("/mnt/e/local-model-run/tmp/pertask")
fails = []
for spec in HARD_REGISTRY:
    d = materialize_all([spec], root / spec.task_id)[0]
    task = load_task(d)
    out = p.generate(task.prompt, seed=0, temperature=0.0,
                     max_new_tokens=task.max_new_tokens, system=task.system)
    ok = oracle.verify(out.text, task).passed
    print(f"{'PASS' if ok else 'FAIL'}  {spec.task_id}")
    if not ok:
        fails.append(spec.task_id)
print(f"\ngreedy single-shot fails: {fails}")
