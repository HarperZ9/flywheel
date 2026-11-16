"""Reference-build a shared_task_artifact/v2 participant envelope."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURE = Path("benchmarks/fixtures/cross-harness/shared-task-facts-v2.json")
CONTEXT = Path("benchmark/context.json")


def j(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def claim_bindings(fixture, values):
    rows = json.loads(json.dumps(fixture["participant_contract"]["claim_bindings"]))
    facts = rows[0]["facts"]
    states = values["orthogonal_states"]
    facts["execution_state"] = states["execution_state"]
    facts["oracle_state"] = states["oracle_state"]
    facts["receipt_state"] = states["receipt_state"]
    facts["pre_oracle_failure_modes"] = values.get("pre_oracle_failure_modes", values.get("failure_modes", []))
    return rows


def render(report, fixture):
    facts = report["claim_bindings"][0]["facts"]
    replacements = {
        "task_id": report["task_id"],
        "input_sha256s": j(report["input_sha256s"]),
        "raw_prompt_sha256": j(report["raw_prompt_sha256"]),
        "tool_policy_sha256": j(report["tool_policy_sha256"]),
        "raw_artifact_path": j(report["raw_artifact_path"]),
        "receipt_path": j(report["receipt_path"]),
        "execution_state": j(facts["execution_state"]),
        "oracle_state": j(facts["oracle_state"]),
        "receipt_state": j(facts["receipt_state"]),
        "pre_oracle_failure_modes": j(facts["pre_oracle_failure_modes"]),
    }
    lines = []
    for line in fixture["participant_contract"]["markdown_template"]:
        lines.append(line.format(**replacements))
    return "\n".join(lines) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    fixture = load(FIXTURE)
    context = load(CONTEXT)
    values = context["harness_values"]
    report = {
        "task_id": values["task_id"],
        "input_sha256s": values["input_sha256s"],
        "raw_prompt_sha256": values["raw_prompt_sha256"],
        "tool_policy_sha256": values["tool_policy_sha256"],
        "raw_artifact_path": values["raw_artifact_path"],
        "receipt_path": values["receipt_path"],
        "pre_oracle_failure_modes": values.get("pre_oracle_failure_modes", values.get("failure_modes", [])),
        "claim_bindings": claim_bindings(fixture, values),
    }
    markdown = render(report, fixture)
    json_name, md_name = context["expected_artifacts"]
    print(json.dumps({"artifacts": {json_name: report, md_name: markdown}}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
