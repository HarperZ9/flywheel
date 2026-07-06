"""Run ONE held-out task through the loop against the live server; show the
candidate the oracle actually saw and the pytest error. Pinpoints the 0%."""
import sys
from pathlib import Path
sys.path.insert(0, "/mnt/c/dev/local-model")

from harness.tasks_lib import REGISTRY, materialize_all
from harness.task import load_task
from harness.proposer import ServeProposer
from harness.oracle import PytestOracle
from harness.loop import run_loop

tmp = Path("/mnt/e/local-model-run/tmp/dbg1")
d = materialize_all(REGISTRY[:1], tmp / "tasks")[0]     # the 'add' task
task = load_task(d)
print("task_id:", task.task_id)
print("prompt:", repr(task.prompt[:200]))
print("oracle_cmd:", task.oracle_cmd, "| candidate_path:", task.candidate_path,
      "| max_new_tokens:", task.max_new_tokens)

p = ServeProposer("http://127.0.0.1:8765")
out = p.generate(task.prompt, seed=task.seed, temperature=0.0,
                 max_new_tokens=task.max_new_tokens, system=task.system)
print("\nEXTRACTED CANDIDATE the oracle will see:")
print(repr(out.text))

orc = PytestOracle().verify(out.text, task)
print("\noracle passed:", orc.passed, "rc:", orc.rc)
print("oracle stdout excerpt:")
print(orc.stdout_excerpt[:1200])
