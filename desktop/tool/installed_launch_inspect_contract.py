"""Inspect-specific receipt contract fragments for installed acceptance."""

INSPECT_ASSERTION_IDS = (
    "H21_inspect_fixture_hash_bound",
    "H22_inspect_journey_seeded_in_isolated_profile",
    "H23_inspect_grant_prepare_approve_bound_to_upload",
    "H24_inspect_upload_exact_bytes_accepted",
    "H25_inspect_false_success_controls_rejected",
    "H26_inspect_reopen_after_engine_restart_matches_upload",
    "H27_inspect_list_redacts_report_and_names_eid",
    "H28_inspect_store_tamper_detected",
    "H29_inspect_api_receipt_does_not_claim_desktop_ui",
)
INSPECT_PHASE_ID = "P7_installed_inspect_import_reopen_api"
INSPECT_PHASE_ASSERTIONS = {INSPECT_PHASE_ID: INSPECT_ASSERTION_IDS}
INSPECT_REQUIRED_ASSERTIONS = frozenset((
    "H01_app_exe_exists", "H02_engine_exe_exists_under_install_root",
    "H08_port_precheck_refuses_foreign_gateway",
    "H09_installed_engine_owned_start", "H10_desktop_status_schema_required",
    "H11_token_used_but_redacted", "H12_owned_process_cleanup_no_survivors",
    "H15_offline_to_ready_status_transition",
    "H16_restart_same_isolated_profile",
    "H20_receipt_fresh_complete_and_source_bound",
    *INSPECT_ASSERTION_IDS,
))
