import json
import shutil
from pathlib import Path

import pytest

from harness import source_context_route as route
from harness.evidence_json import canonical_sha256
from harness.source_context_store import (
    SourceContextError, SourceContextStore, _json_file,
)
from tests.test_source_context_route import FakeGather, NoopGuard, OWNER, NOW
from tests.test_source_context_store import CORPUS_ID, ROOT_ID, _selection


def _refresh_selection_digest(payload):
    base = {key: value for key, value in payload.items()
            if key not in {"selection_digest", "verified", "verified_scope"}}
    return dict(payload, selection_digest=canonical_sha256(base))

def test_default_adapter_preserves_guarded_state_root_identity(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    payload = _selection()
    class Adapter:
        last_identity = {"platform": "test", "file_index": 3}
        last_identities = (
            {"path_sha256": route._plain_path_sha(state),
             "platform": "test", "file_index": 12345},
        )
        def __init__(self, **_kwargs): pass
        def select(self, *_args, **_kwargs): return payload
    monkeypatch.setattr(route, "GatherPathAdapter", Adapter)

    _selected, ids = route._guarded_call(
        state / "corpus", None, None, "select", selections=[],
        expected_corpus_digest="c" * 64, caps={}, state_root=state)

    assert ids["state_root_identity"]["file_index"] == 12345


def test_caps_rejected_before_gather_or_admission_lookup(tmp_path):
    root = tmp_path / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    root.mkdir(parents=True)
    gather = FakeGather()

    body, status = route.source_context_post(
        "/api/source-context/attach", json.dumps({
            "schema": "flywheel.source-context-request/v1",
            "root_mode": "flywheel_corpus", "profile": "demo",
            "corpus": "tiny", "expected_corpus_digest": "c" * 64,
            "max_total_chars": 100_001,
            "selections": [{"row_ref": "row_abc", "start": 0, "limit": 19}],
        }).encode(), owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        gather=gather, guard_cls=NoopGuard)

    assert status == 422
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert gather.calls == []


def test_unadmitted_flywheel_corpus_does_not_call_gather(tmp_path):
    root = tmp_path / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    root.mkdir(parents=True)
    gather = FakeGather()

    body, status = route.source_context_post(
        "/api/source-context/attach", json.dumps({
            "schema": "flywheel.source-context-request/v1",
            "root_mode": "flywheel_corpus", "profile": "demo",
            "corpus": "tiny", "expected_corpus_digest": "c" * 64,
            "selections": [{"row_ref": "row_abc", "start": 0, "limit": 19}],
        }).encode(), owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        gather=gather, guard_cls=NoopGuard)

    assert status == 409
    assert body["error"]["code"] == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    assert gather.calls == []


def test_copied_snapshot_to_different_state_root_rejects_resolution(tmp_path):
    state_a, state_b = tmp_path / "state-a", tmp_path / "state-b"
    state_a.mkdir()
    store_a = SourceContextStore(state_a)
    attached = store_a.publish_selection(
        owner_ref=OWNER, state_root_identity=store_a.state_root_identity(),
        root_mode="flywheel_corpus", profile="demo", corpus_locator="tiny",
        corpus_root_identity=CORPUS_ID, gather_payload=_selection(),
        selected_at="one")
    shutil.copytree(state_a, state_b)

    with pytest.raises(SourceContextError):
        SourceContextStore(state_b).resolve_worker_payload(
            OWNER, (attached["source_context_ref"],))


def test_binding_state_root_profile_and_schema_substitution_rejected(tmp_path):
    store = SourceContextStore(tmp_path, expected_state_root_identity=ROOT_ID)
    attached = store.publish_selection(
        owner_ref=OWNER, state_root_identity=ROOT_ID, root_mode="flywheel_corpus",
        profile="demo", corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
        gather_payload=_selection(), selected_at="one")
    binding = (tmp_path / "source-context" / "v1" / "owners" / OWNER
               / "bindings" / f"{attached['private_payload_sha256']}.json")
    body = json.loads(binding.read_text(encoding="utf-8"))
    body["schema"] = "wrong-schema"
    body["profile"] = "wrong-profile"
    body["state_root_identity"] = {"platform": "wrong-root"}
    binding.write_text(json.dumps(body), encoding="utf-8")

    with pytest.raises(SourceContextError):
        store.resolve_worker_payload(OWNER, (attached["source_context_ref"],))


def test_unverified_gather_payload_or_bad_selection_digest_is_not_published(tmp_path):
    bad = dict(_selection(), verified=False, verified_scope="none",
               selection_digest="0" * 64)

    with pytest.raises(SourceContextError):
        SourceContextStore(tmp_path, expected_state_root_identity=ROOT_ID).publish_selection(
            owner_ref=OWNER, state_root_identity=ROOT_ID,
            root_mode="flywheel_corpus", profile="demo",
            corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
            gather_payload=bad, selected_at="one")


def test_gather_omission_host_path_is_not_published_to_projection(tmp_path):
    bad = _selection()
    bad["omissions"] = [{"code": "PRIVATE_PATH", "ref": "C:/private/secret.txt"}]
    bad = _refresh_selection_digest(bad)

    with pytest.raises(SourceContextError) as exc:
        SourceContextStore(tmp_path, expected_state_root_identity=ROOT_ID).publish_selection(
            owner_ref=OWNER, state_root_identity=ROOT_ID,
            root_mode="flywheel_corpus", profile="demo",
            corpus_locator="tiny", corpus_root_identity=CORPUS_ID,
            gather_payload=bad, selected_at="one")
    assert exc.value.code == "SOURCE_CONTEXT_SELECTION_FAILED"

def test_oversized_private_json_is_rejected_without_full_read(tmp_path, monkeypatch):
    path = tmp_path / "oversize.json"
    path.write_bytes(b" " * 2_000_000)
    reads = []
    original = Path.read_bytes
    def observed_read(self):
        data = original(self)
        if self == path:
            reads.append(len(data))
        return data
    monkeypatch.setattr(Path, "read_bytes", observed_read)

    with pytest.raises(SourceContextError):
        _json_file(path, max_bytes=1_000_000)

    assert reads == []

