import unittest

from control_outcome import EXPECTED_LOG_MODEL, EXPECTED_SCORER_NAME, classify_control


def base_summary():
    return {
        "logs_count": 1,
        "log_status": "success",
        "log_error": None,
        "log_eval_model": EXPECTED_LOG_MODEL,
        "task_name": "count_odds",
        "task_version": "0.0.1",
        "sample_count": 1,
        "sample_id": "hard",
        "sample_error": None,
        "solver_event_count": 1,
        "score_name": EXPECTED_SCORER_NAME,
        "bridge_task_shape": {
            "has_setup": True,
            "has_scorer": True,
            "has_cleanup": True,
        },
    }


class ControlClassificationTests(unittest.TestCase):
    def test_correct_control_passes_exact_score(self):
        summary = base_summary() | {"score_value": 1.0}
        self.assertEqual(classify_control(summary, expected_value=1.0)["status"], "pass")

    def test_wrong_control_requires_observed_zero(self):
        summary = base_summary() | {"score_value": 0.0}
        self.assertEqual(classify_control(summary, expected_value=0.0)["status"], "pass")

    def test_no_submit_tool_call_does_not_pass_on_missing_sample(self):
        summary = base_summary() | {"sample_count": 0, "sample_id": None, "score_value": None}
        result = classify_control(summary, expected_value=None, must_not_equal=1.0)
        self.assertEqual(result["status"], "fail")
        self.assertIn("expected_exactly_one_sample", result["reasons"])

    def test_no_submit_tool_call_does_not_pass_on_task_error(self):
        summary = base_summary() | {"sample_error": "boom", "score_value": 0.0}
        result = classify_control(summary, expected_value=None, must_not_equal=1.0)
        self.assertEqual(result["status"], "fail")
        self.assertIn("sample_error_present", result["reasons"])

    def test_no_submit_tool_call_does_not_pass_on_nonfinite_score(self):
        summary = base_summary() | {"score_value": {"kind": "nonfinite", "repr": "nan"}}
        result = classify_control(summary, expected_value=None, must_not_equal=1.0)
        self.assertEqual(result["status"], "fail")
        self.assertIn("score_nonfinite", result["reasons"])

    def test_no_submit_tool_call_requires_finite_real_numeric_score(self):
        invalid_values = [None, "0", {"value": 0}, [0], False, True]
        for value in invalid_values:
            with self.subTest(value=value):
                summary = base_summary() | {"score_value": value}
                result = classify_control(summary, expected_value=None, must_not_equal=1.0)
                self.assertEqual(result["status"], "fail")
                self.assertTrue(
                    any(reason.startswith("score_not_finite_real_observed_") for reason in result["reasons"]),
                    result["reasons"],
                )

    def test_no_submit_tool_call_finite_zero_is_valid_negative_evidence(self):
        summary = base_summary() | {"score_value": 0.0}
        self.assertEqual(
            classify_control(summary, expected_value=None, must_not_equal=1.0)["status"],
            "pass",
        )

    def test_unexpected_scorer_name_fails(self):
        summary = base_summary() | {"score_name": "other_scorer", "score_value": 0.0}
        result = classify_control(summary, expected_value=None, must_not_equal=1.0)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(
            any(reason.startswith("unexpected_score_name_expected_") for reason in result["reasons"]),
            result["reasons"],
        )

    def test_missing_scorer_name_fails(self):
        summary = base_summary() | {"score_name": None, "score_value": 0.0}
        result = classify_control(summary, expected_value=None, must_not_equal=1.0)
        self.assertEqual(result["status"], "fail")
        self.assertIn("score_not_observed", result["reasons"])

    def test_external_or_default_eval_model_fails(self):
        summary = base_summary() | {"log_eval_model": "openai/gpt-4o-mini", "score_value": 0.0}
        result = classify_control(summary, expected_value=None, must_not_equal=1.0)
        self.assertEqual(result["status"], "fail")
        self.assertTrue(
            any(reason.startswith("unexpected_eval_model_expected_") for reason in result["reasons"]),
            result["reasons"],
        )


if __name__ == "__main__":
    unittest.main()
