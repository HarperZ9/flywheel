import unittest
import tomllib

from tools.behavior_flagship import (
    ROOT,
    SCHEMA,
    demo_envelope,
    doctor_envelope,
    status_envelope,
)


class BehaviorFlagshipTests(unittest.TestCase):
    def test_status_uses_telos_schema(self) -> None:
        envelope = status_envelope()

        self.assertEqual(envelope["schema"], SCHEMA)
        self.assertEqual(envelope["tool"], "behavior-transform.io")
        self.assertEqual(envelope["status"], "MATCH")
        self.assertIn("CLI JSON", envelope["native"]["host_surfaces"])
        self.assertFalse(envelope["native"]["runtime_contract"]["raw_secret_export"])

    def test_doctor_checks_contract_and_secret_boundary(self) -> None:
        envelope = doctor_envelope()
        checks = {
            item["id"]: item
            for output in envelope["outputs"]
            if output["kind"] == "checks"
            for item in output["items"]
        }

        self.assertIn("required:docs/INTEGRATION_CONTRACT.md", checks)
        self.assertIn("raw-secret-boundary", checks)
        self.assertEqual(envelope["status"], "MATCH")

    def test_doctor_requires_operator_docs_and_console_scripts(self) -> None:
        envelope = doctor_envelope()
        checks = {
            item["id"]: item
            for output in envelope["outputs"]
            if output["kind"] == "checks"
            for item in output["items"]
        }

        for rel in ("AGENTS.md", "USAGE.md"):
            self.assertIn(f"required:{rel}", checks)
            self.assertEqual(checks[f"required:{rel}"]["status"], "MATCH")

        self.assertEqual(checks["console-script:behavior-transform"]["status"], "MATCH")
        self.assertEqual(checks["console-script:behavior-transform-io"]["status"], "MATCH")

    def test_pyproject_exposes_installable_cli_scripts(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = data["project"]["scripts"]

        self.assertEqual(scripts["behavior-transform"], "tools.behavior_flagship:main")
        self.assertEqual(scripts["behavior-transform-io"], "tools.behavior_flagship:main")

    def test_readme_links_operator_and_usage_docs(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("[AGENTS.md](AGENTS.md)", readme)
        self.assertIn("[USAGE.md](USAGE.md)", readme)

    def test_demo_is_local_io_only(self) -> None:
        envelope = demo_envelope()
        demo = envelope["outputs"][0]

        self.assertEqual(demo["runtime_surface"], "local_io")
        self.assertIn("switch back to ops calibration", demo["steps"])


if __name__ == "__main__":
    unittest.main()
