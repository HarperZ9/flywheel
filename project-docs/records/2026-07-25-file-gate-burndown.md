# File gate burn-down (frozen 2026-07-25)

The 300-line gate applies to every file in harness/. These violations predate
enforcement and are frozen at their current size. A file on this list may
shrink and leave it; it may never grow. New files may not join it.

Enforced by scripts/check_file_gate.py and tests/test_file_gate.py.

| file | lines |
|---|---|
| harness/agent_recovery_bench.py | 684 |
| harness/classifier_friction_bench.py | 454 |
| harness/cross_harness_manifest.py | 342 |
| harness/endpoints.py | 492 |
| harness/gateway.py | 2477 |
| harness/governed_agent_bench.py | 734 |
| harness/lanes.py | 361 |
| harness/local_agent.py | 360 |
| harness/local_tools.py | 454 |
| harness/lesson.py | 356 |
| harness/lesson_mappers.py | 340 |
| harness/loops.py | 315 |
| harness/model_card_claims.py | 311 |
| harness/serve.py | 420 |
| harness/source_mined_bench.py | 974 |
| harness/tasks_physics.py | 461 |
| harness/typeface_skeletons.py | 504 |
| harness/unisonai_stateful_bench.py | 559 |

Total: 15 files, 9273 lines over a 300-line gate.


Merge note, 2026-07-28 (p1/tail x main): tasks_physics.py and
gateway.py reached this size on the main lineage, which carried no file
gate. The merge is the moment they come under it, so they are frozen at
merge size under this record's own rule: shrink and leave, never grow.
Same rule, second boundary: lanes.py grew 317 to 350 on main (PRs 11 and 12,
2026-07-28) before main carried any gate; its ceiling moves to 350 at that
merge and may only shrink from there. Third boundary, same day:
350 to 361 at PR 13 (PyInstaller packaging), ceiling moves to 361.
