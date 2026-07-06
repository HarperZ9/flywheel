"""provenance-keyed flywheel falsifier (#4) — stale knowledge invalidates cheaply.

The latent bug: cache_key bound the task/prompt/oracle-input but NOT the retrieved
KNOWLEDGE, so a result grounded on a source that later DRIFTED could be served
stale. Fix: knowledge_hash binds the cited receipts into the key.

Properties:
  1. a task with no citations keys exactly as before (backward compatible);
  2. changing the cited knowledge changes the key (a miss -> re-verify);
  3. identical knowledge keys identically (a hit).
"""
from dataclasses import replace

from harness.cache import cache_key, knowledge_hash
from harness.task import load_task, Retrieved
from pathlib import Path

TASK_DIR = Path(__file__).parent.parent / "tasks" / "example_pass"


def _task(tmp_path, cites):
    t = load_task(TASK_DIR, workdir=tmp_path / "w")
    return replace(t, retrieved=[Retrieved(source=s, receipt=r) for s, r in cites])


def test_no_citations_is_backward_compatible(tmp_path):
    t = load_task(TASK_DIR, workdir=tmp_path / "w")
    assert knowledge_hash(t) == ""
    # key with empty knowledge == key computed the old way (no knowledge arg)
    k_new = cache_key(t, "ph", "m", 0, "cmd", knowledge_hash(t))
    k_old = cache_key(t, "ph", "m", 0, "cmd")
    assert k_new == k_old


def test_changed_knowledge_changes_the_key(tmp_path):
    t1 = _task(tmp_path, [("srcA", "receipt-v1")])
    t2 = _task(tmp_path, [("srcA", "receipt-v2")])   # same source, DRIFTED receipt
    k1 = cache_key(t1, "ph", "m", 0, "cmd", knowledge_hash(t1))
    k2 = cache_key(t2, "ph", "m", 0, "cmd", knowledge_hash(t2))
    assert k1 != k2, "a drifted cited source must change the key (no stale serve)"


def test_identical_knowledge_keys_identically(tmp_path):
    t1 = _task(tmp_path, [("srcA", "r1"), ("srcB", "r2")])
    t2 = _task(tmp_path, [("srcB", "r2"), ("srcA", "r1")])   # order-independent
    assert knowledge_hash(t1) == knowledge_hash(t2)
    assert (cache_key(t1, "ph", "m", 0, "cmd", knowledge_hash(t1))
            == cache_key(t2, "ph", "m", 0, "cmd", knowledge_hash(t2)))


def test_citations_change_key_vs_no_citations(tmp_path):
    t0 = load_task(TASK_DIR, workdir=tmp_path / "w")
    t1 = _task(tmp_path, [("srcA", "r1")])
    assert (cache_key(t0, "ph", "m", 0, "cmd", knowledge_hash(t0))
            != cache_key(t1, "ph", "m", 0, "cmd", knowledge_hash(t1)))
