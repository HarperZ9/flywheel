import json

from harness.evidence_json import canonical_sha256
from harness.gateway_agent_trace import AgentTrace, TraceLedger
from harness.gateway_operation_process import WorkerOutcome
from tests.test_gateway_operations import JOURNEY, OWNER, _service
from tests.test_gateway_operation_recovery import OPERATION, _queued, _started


def test_self_hashed_worker_effect_summary_seals_typed_failure(tmp_path):
    _started(tmp_path, _queued(tmp_path))
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
    TraceLedger(trace).append("tool_result", "private result", {
        "tool": "write_file", "ok": True,
        "edited": {"worker.txt": "a" * 64},
    })
    projection = trace.projection("completed")
    projection.pop("projection_sha256")
    projection["effect_evidence"] = {"schema": "worker-supplied"}
    projection["projection_sha256"] = canonical_sha256(projection)
    service = _service(tmp_path)

    terminal = service._terminal(
        OWNER, OPERATION, WorkerOutcome("completed", projection))
    result = service.result(OWNER, OPERATION)["result"]

    assert terminal.state == "failed"
    assert result == {"reason": "EXTERNAL_ACTION_FAILED"}
    assert "worker-supplied" not in json.dumps(result)
