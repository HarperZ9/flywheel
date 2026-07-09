import json

from scripts.run_tool_hardening_plan import action_items_for_tool, build_plan, main


def test_action_items_separate_observation_from_inference():
    tool = {
        "tool": "relay",
        "root": "C:/dev/public/relay",
        "root_exists": True,
        "categories": {
            "core": {"required": 1, "present": 1, "score": 1.0, "missing_files": []},
            "enterprise": {"required": 1, "present": 0, "score": 0.0, "missing_files": ["SECURITY.md"]},
            "integration": {"required": 1, "present": 0, "score": 0.0, "missing_files": ["serve.py"]},
        },
    }

    actions = action_items_for_tool(tool)

    assert [action["priority"] for action in actions] == ["P2", "P1"]
    assert actions[0]["observation"].startswith("`SECURITY.md` is missing")
    assert "Document vulnerability disclosure" in actions[0]["inference"]
    assert actions[1]["owner"] == "platform-integration"


def test_build_plan_emits_release_gates_and_priority_counts():
    readiness = {
        "schema": "harness.tool-readiness/v1",
        "tools": [
            {
                "tool": "mneme",
                "root": "C:/dev/public/mneme",
                "root_exists": True,
                "categories": {
                    "core": {"required": 1, "present": 1, "score": 1.0, "missing_files": []},
                    "enterprise": {"required": 1, "present": 0, "score": 0.0, "missing_files": ["SECURITY.md"]},
                    "integration": {"required": 1, "present": 1, "score": 1.0, "missing_files": []},
                },
            }
        ],
    }

    plan = build_plan(readiness, readiness_artifact="tool_readiness.json")

    assert plan["schema"] == "harness.tool-hardening-plan/v1"
    assert plan["summary"]["actions"] == 1
    assert plan["summary"]["p2_actions"] == 1
    assert plan["summary"]["release_gates"] == 4
    assert plan["summary"]["enterprise_ready_static"] is False


def test_build_plan_marks_missing_source_as_not_enterprise_ready():
    plan = build_plan(
        {"schema": "", "tools": []},
        readiness_artifact="missing_tool_readiness.json",
        source_loaded=False,
        source_load_error="missing_artifact",
    )

    assert plan["summary"]["source_loaded"] is False
    assert plan["summary"]["source_load_error"] == "missing_artifact"
    assert plan["summary"]["enterprise_ready_static"] is False


def test_missing_tool_root_creates_p0_restore_action():
    tool = {
        "tool": "plexus",
        "root": "C:/dev/public/plexus",
        "root_exists": False,
        "categories": {},
    }

    actions = action_items_for_tool(tool)

    assert actions[0]["priority"] == "P0"
    assert "Tool root is missing" in actions[0]["observation"]


def test_main_writes_plan_and_store_receipt(tmp_path):
    readiness = tmp_path / "tool_readiness.json"
    readiness.write_text(json.dumps({
        "schema": "harness.tool-readiness/v1",
        "tools": [
            {
                "tool": "relay",
                "root": "C:/dev/public/relay",
                "root_exists": True,
                "categories": {
                    "core": {"required": 1, "present": 1, "score": 1.0, "missing_files": []},
                    "enterprise": {"required": 1, "present": 0, "score": 0.0, "missing_files": ["SECURITY.md"]},
                    "integration": {"required": 1, "present": 0, "score": 0.0, "missing_files": ["serve.py"]},
                },
            }
        ],
    }), encoding="utf-8")
    out = tmp_path / "plan.json"
    md = tmp_path / "plan.md"
    store = tmp_path / "store"

    code = main([
        "--readiness-artifact",
        str(readiness),
        "--out",
        str(out),
        "--markdown-out",
        str(md),
        "--store-root",
        str(store),
        "--run-id",
        "run_tools",
    ])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert data["summary"]["actions"] == 2
    assert data["store_outputs"][0]["schema"] == "harness.receipt/v1"
    assert "# Tool enterprise hardening plan" in md.read_text(encoding="utf-8")


def test_main_missing_readiness_artifact_is_unverifiable_not_ready(tmp_path):
    missing = tmp_path / "missing_tool_readiness.json"
    out = tmp_path / "plan.json"

    code = main([
        "--readiness-artifact",
        str(missing),
        "--out",
        str(out),
    ])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert data["summary"]["source_loaded"] is False
    assert data["summary"]["enterprise_ready_static"] is False
    assert data["load_error"] == "missing_artifact"
