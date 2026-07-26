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
| harness/gateway.py | 2421 |
| harness/governed_agent_bench.py | 734 |
| harness/lanes.py | 317 |
| harness/local_agent.py | 360 |
| harness/local_tools.py | 386 |
| harness/loops.py | 315 |
| harness/model_card_claims.py | 311 |
| harness/serve.py | 420 |
| harness/source_mined_bench.py | 974 |
| harness/typeface_skeletons.py | 504 |
| harness/unisonai_stateful_bench.py | 559 |

Total: 15 files, 9273 lines over a 300-line gate.
