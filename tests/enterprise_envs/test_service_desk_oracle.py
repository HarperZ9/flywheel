def test_oracle_rejects_model_submitted_logs_and_missing_server_events(tmp_path):
    """Catches oracles that trust client-submitted logs or final prose."""
    from tests.enterprise_envs.package_helpers import add_product_src

    add_product_src()
    from service_desk_incident_env.v1.calibration_cases import run_calibration

    receipt = run_calibration(tmp_path)
    failures = {case["case_id"]: case for case in receipt["case_results"]}

    assert receipt["false_accepts"] == 0
    assert failures["bad_client_submitted_log"]["observed_state"] == "fail"
    assert "model_submitted_log_credited" in failures["bad_client_submitted_log"]["failure_codes"]
    assert failures["bad_mutation_without_log"]["observed_state"] == "fail"
    assert "server_action_log_missing" in failures["bad_mutation_without_log"]["failure_codes"]
    assert failures["wrong_attachment_target"]["observed_state"] == "fail"
    assert "target_attachment_missing" in failures["wrong_attachment_target"]["failure_codes"]
    assert failures["closed_target_incident"]["observed_state"] == "fail"
    assert "target_incident_not_open" in failures["closed_target_incident"]["failure_codes"]


def test_oracle_binds_attachment_to_payroll_incident_and_keeps_it_open(tmp_path):
    """Catches task passes that attach evidence elsewhere or close the target incident."""
    from tests.enterprise_envs.package_helpers import add_product_src

    add_product_src()
    from service_desk_incident_env.v1.calibration_cases import run_calibration

    receipt = run_calibration(tmp_path)
    case_ids = {case["case_id"] for case in receipt["case_results"]}

    assert {"wrong_attachment_target", "closed_target_incident"} <= case_ids
    assert receipt["false_accepts"] == 0
