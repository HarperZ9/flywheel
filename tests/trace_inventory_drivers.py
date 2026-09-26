"""Representative writers for the I2 dynamic sweep.

Each driver calls a real Flywheel writer, not a stand-in, against the
temporary FLYWHEEL_HOME and run root the sweep points it at. A package that
adds a store adds its driver here, so the sweep grows with the code.
"""
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
OPERATION = "op_" + "c" * 32
CLOCK = "2026-09-26T12:00:00Z"


def agent_trace(home, run_root):
    from harness.gateway_agent_trace import AgentTrace
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    trace = AgentTrace(state, OWNER, JOURNEY, OPERATION)
    trace.append("result", {"final": "sweep", "duration_s": 0.01})


def scaffold(home, run_root):
    from harness.scaffold import scaffold_answer, scaffold_turn
    from harness.web_snapshot import snapshot_url

    def snapshotter(url):
        return snapshot_url(url, run_root / "snapshots", runner=lambda u: (
            200, {"Content-Type": "text/plain"}, b"sweep page", u))
    envelope = scaffold_turn("see https://example.invalid/sweep", snapshotter=snapshotter)
    scaffold_answer("sweep answer", envelope)


def memory_note(home, run_root):
    from harness.memory_api import memory_note as note
    note(run_root, "a sweep note")


def operations(home, run_root):
    from harness.gateway_operation_process import WorkerOutcome
    from harness.gateway_operation_route import route_gateway_operation
    from gateway_route_fixtures import OWNER as FIXTURE_OWNER, Factory, Process, _setup
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    service, raw = _setup(state, stream=False)
    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=FIXTURE_OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=Factory(Process(WorkerOutcome("completed", {"final": "ok"}))))
    assert response.status == 200


def grants(home, run_root):
    from harness.operation_grants import GrantRequest, GrantStore
    store = GrantStore(home / "state", clock=lambda: CLOCK)
    store.issue(GrantRequest(OWNER, None, None, "a" * 64, "journey.create", "b" * 64,
                             ("write",), (), None, "sweep-nonce"), approved=True)


def continuation(home, run_root):
    from harness.continuation_store import write_preview
    from harness.evidence_json import canonical_sha256
    preview = {"preview_ref": "cpv_" + "d" * 32, "summary_sha256": "e" * 64}
    preview["preview_sha256"] = canonical_sha256(preview)
    write_preview(home / "state", preview, {"schema": "sweep-intake/v1", "count": 1})


def source_context(home, run_root):
    from harness.private_artifact_fs import root_identity
    from harness.source_context_store import SourceContextStore
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    import test_source_context_store as fixture  # the store's own payload builder
    store = SourceContextStore(state, clock=lambda: CLOCK)
    store.publish_selection(
        owner_ref=OWNER, state_root_identity=store.state_root_identity(),
        root_mode="flywheel_corpus", profile="demo", corpus_locator="tiny",
        corpus_root_identity=root_identity(state).to_json_dict(),
        gather_payload=fixture._selection("SWEEP-SOURCE"), selected_at=CLOCK)


DRIVERS = (agent_trace, scaffold, memory_note, operations, grants,
           continuation, source_context)


def run_all(home, run_root):
    """Run every driver; return the ones that raised, by name and error type."""
    failed = {}
    for driver in DRIVERS:
        try:
            driver(home, run_root)
        except Exception as exc:  # the sweep reports; the test asserts
            failed[driver.__name__] = f"{type(exc).__name__}: {exc}"
    return failed
