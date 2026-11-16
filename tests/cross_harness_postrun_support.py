import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from harness.cross_harness_executor import execute_cross_harness_manifest
from harness.cross_harness_types import AdapterResult, AvailabilityResult, EnforcementResult

TASK_ID = "agt-003-codex-flywheel-shared-task"
ROLES = ("codex_harness", "flywheel_harness")
SOURCE_COMMIT = "b255cee18700338ae8bef122170ef472e71e25a7"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _refresh_index_hashes(run_root):
    index = run_root / "artifact-index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    for item in data["artifacts"]:
        path = run_root / item["path"]
        if path.exists() and path.is_file():
            item["sha256"] = _sha(path)
    _write_json(index, data)


def _make_dir_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            pytest.skip("directory symlinks unavailable")
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        pytest.skip(f"directory link unavailable: {result.stderr or result.stdout}")


def _shared_fixture(source):
    fixture = source / "benchmarks" / "fixtures" / "cross-harness" / "shared-task-facts-v1.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(Path("benchmarks/fixtures/cross-harness/shared-task-facts-v1.json").read_text(encoding="utf-8"), encoding="utf-8")
    return fixture.relative_to(source).as_posix(), _sha(fixture)


def _manifest(source):
    fixture, digest = _shared_fixture(source)
    prompt = "Run or prepare the same bounded repo-grounded task.\n"
    return {"task_set_id": "set", "task_rows": [{"task_id": TASK_ID, "raw_prompt": prompt,
        "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "input_sha256s": {fixture: digest},
        "required_inputs": [fixture], "expected_artifacts": ["codex_flywheel_shared_task_scorecard.json", "codex_flywheel_shared_task_scorecard.md"],
        "oracle": {"checker_id": "shared_task_artifact/v1", "fixture": fixture,
                   "expected_artifacts": ["codex_flywheel_shared_task_scorecard.json", "codex_flywheel_shared_task_scorecard.md"]}}],
        "provider_specs": [
            {"provider_role": "codex_harness", "harness_id": "codex", "adapter_id": "codex_cli_json/v1",
             "model_id": "gpt-5.3-codex-spark", "model_display_name": "GPT-5.3-Codex-Spark", "requested_model_reference": "gpt-5.3-codex-spark"},
            {"provider_role": "flywheel_harness", "harness_id": "flywheel", "adapter_id": "flywheel_router/v1",
             "model_id": "gpt-5.3-codex-spark", "model_display_name": "GPT-5.3-Codex-Spark", "requested_model_reference": "gpt-5.3-codex-spark"},
        ]}


def _runtime(roles=ROLES, *, ready=True):
    return {"runtime_rows": [{"provider_role": role, "focused_run_ready": ready,
        "blocking_gates": [] if ready else ["spark_unavailable"],
        "endpoint_profile_matches": [], "endpoint_gate_matches": []} for role in roles]}


class PairAdapter:
    def __init__(self, role, adapter_id, output):
        self.role = role
        self.adapter_id = adapter_id
        self.output = output

    def enforcement(self, request):
        description = {"boundary": self.role, "declared_policy": request.tool_policy["version"]}
        return EnforcementResult(description, _canonical_sha(description), "unverified_claim", "non_equivalent")

    def availability(self, request):
        return AvailabilityResult(True, "", "ready", {"provider_called": False})

    def execute(self, request):
        return AdapterResult("returned", self.output(request), [], 5, "gpt-5.3-codex-spark", "unsupported", "", "",
                             {"provider_reported_cost_usd": 0.01}, {"output_tokens": 12}, ["read"], [], "structured_provider_response")


def _shared_output(request, *, fail=False):
    report = {"task_id": request.task_id, "input_sha256s": request.input_sha256s,
              "raw_prompt_sha256": request.raw_prompt_sha256, "tool_policy_sha256": request.tool_policy_sha256,
              "raw_artifact_path": "output.txt", "receipt_path": "provider-receipt.json",
              "failure_modes": ["unavailable"] if fail else []}
    return json.dumps({"artifacts": {
        "codex_flywheel_shared_task_scorecard.json": report,
        "codex_flywheel_shared_task_scorecard.md": f"# {request.task_id}\n"
    }})


def _execute_pair(tmp_path, *, flywheel_fails=True, roles=ROLES, ready=True):
    source = tmp_path / "source"; source.mkdir()
    manifest = _manifest(source)
    manifest["provider_specs"] = [row for row in manifest["provider_specs"] if row["provider_role"] in roles]
    adapters = {
        "codex_harness": PairAdapter("codex_harness", "codex_cli_json/v1", lambda request: _shared_output(request)),
        "flywheel_harness": PairAdapter("flywheel_harness", "flywheel_router/v1", lambda request: _shared_output(request, fail=flywheel_fails)),
    }
    return execute_cross_harness_manifest(manifest, _runtime(roles, ready=ready), {role: adapters[role] for role in roles},
        artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="spark",
        selectors=["agt-003"], roles=list(roles), repetitions=1, source_commit=SOURCE_COMMIT), tmp_path / "artifacts" / "run"
