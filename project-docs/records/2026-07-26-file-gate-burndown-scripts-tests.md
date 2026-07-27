# File gate burn-down: scripts and tests (frozen 2026-07-26)

The 300-line gate applies to every file in scripts/ and tests/ as well as
harness/. These violations predate enforcement of the gate over these two
trees and are frozen at their current size. A file on this list may shrink
and leave it; it may never grow. New files may not join it.

The harness/ tree has its own frozen record dated 2026-07-25. Both files are
loaded and merged by scripts/check_file_gate.py; keys are tree-prefixed and
do not collide. Kept separate because each was frozen on the day its tree came
under the gate, and a frozen record should not be rewritten after the fact.

Enforced by scripts/check_file_gate.py and tests/test_file_gate.py.

| file | lines |
|---|---|
| scripts/build_local_harness_exes.py | 740 |
| scripts/model_card_benchmark_shapes.py | 949 |
| scripts/package_local_harness_release.py | 456 |
| scripts/run_benchmark_execution_matrix.py | 654 |
| scripts/run_benchmark_profile_coverage.py | 1298 |
| scripts/run_benchmark_profile_manifest.py | 652 |
| scripts/run_closed_loop_benchmark_seed.py | 1189 |
| scripts/run_closed_loop_outcome_report.py | 2646 |
| scripts/run_endpoint_auth_status.py | 310 |
| scripts/run_flywheel_integration_benchmark.py | 952 |
| scripts/run_harness_architecture_report.py | 701 |
| scripts/run_harness_cli.py | 1554 |
| scripts/run_harness_comparison_report.py | 464 |
| scripts/run_huggingface_release_stage.py | 393 |
| scripts/run_index_receipt.py | 343 |
| scripts/run_local_model_launch_readiness.py | 338 |
| scripts/run_local_model_serve_launcher.py | 336 |
| scripts/run_m7_eval.py | 1119 |
| scripts/run_model_endpoint_gate.py | 333 |
| scripts/run_model_endpoint_profiles.py | 354 |
| scripts/run_model_publish_plan.py | 338 |
| scripts/run_model_release_readiness.py | 550 |
| scripts/run_model_repo_stage.py | 476 |
| scripts/run_package_ship_doctor.py | 394 |
| scripts/run_pubscan_resource_profiles.py | 510 |
| scripts/run_source_mined_backend_matrix.py | 309 |
| scripts/run_tool_hardening_plan.py | 328 |
| scripts/run_tool_integration_contract.py | 350 |
| scripts/run_tool_readiness_receipts.py | 486 |
| scripts/run_unisonai_stateful_benchmark.py | 302 |
| scripts/seed_hard_v2.py | 330 |
| scripts/seed_hard_v2_b2.py | 302 |
| scripts/seed_hard_v2_b4.py | 813 |
| scripts/seed_hard_v2_b5.py | 795 |
| scripts/seed_hard_v2_b6.py | 947 |
| scripts/seed_hard_v2_b7.py | 954 |
| tests/test_benchmark_profile_coverage.py | 589 |
| tests/test_bundle.py | 322 |
| tests/test_closed_loop_benchmark_seed.py | 433 |
| tests/test_closed_loop_outcome_report.py | 1557 |
| tests/test_contest.py | 329 |
| tests/test_gateway.py | 818 |
| tests/test_harness_cli.py | 851 |
| tests/test_ledger.py | 372 |
| tests/test_selector.py | 332 |
| tests/test_unisonai_stateful_bench.py | 364 |

Total: 46 files (36 in scripts/, 10 in tests/), 29932 lines over a 300-line gate.
