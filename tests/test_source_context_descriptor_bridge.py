from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

import pytest

from harness.source_context_store import SourceContextError, SourceContextStore
from tests.test_source_context_route import OWNER
from tests.test_source_context_store import _selection


def _identity_dict(path: Path) -> dict:
    from harness.private_artifact_fs import root_identity

    identity = root_identity(path)
    return {"platform": identity.platform, "device": identity.device,
            "inode": identity.inode}


def test_adapter_passes_borrowed_descriptor_to_gather_not_path(
        monkeypatch, tmp_path):
    from harness import source_context_gather as bridge

    state = tmp_path / "state"
    corpus = state / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    corpus.mkdir(parents=True)

    @dataclass(frozen=True)
    class FakeIdentity:
        platform: str
        device: int
        inode: int

    @dataclass(frozen=True)
    class FakeDescriptor:
        expected_identity: FakeIdentity
        fd: int | None = None
        handle: int | None = None

    seen = []

    def fake_select(corpus_arg, selections, *, expected_corpus_digest, **caps):
        assert isinstance(corpus_arg, FakeDescriptor)
        assert not isinstance(corpus_arg, (str, os.PathLike))
        assert (corpus_arg.fd is None) != (corpus_arg.handle is None)
        if corpus_arg.fd is not None:
            os.fstat(corpus_arg.fd)
        else:
            import harness.private_artifact_fs_windows as windows_backend
            windows_backend._win.handle_info(corpus_arg.handle)
        seen.append((corpus_arg, list(selections), expected_corpus_digest, caps))
        return _selection("DESCRIPTOR-CONTEXT", expected_corpus_digest)

    monkeypatch.setattr(bridge, "_descriptor_api",
        lambda kind, explicit=None: (explicit or fake_select,
            FakeIdentity, FakeDescriptor), raising=False)

    selected = bridge.GatherPathAdapter(select_fn=fake_select).select(
        corpus, [{"row_ref": "row_abc", "start": 0, "limit": 18}],
        expected_corpus_digest="c" * 64,
        expected_identity=_identity_dict(corpus),
        expected_state_identity=_identity_dict(state),
        state_root=state)

    assert selected["selections"][0]["text"] == "DESCRIPTOR-CONTEXT"
    assert seen[0][0].expected_identity == FakeIdentity(**_identity_dict(corpus))


def test_real_gather_descriptor_reads_original_root_after_path_swap(tmp_path):
    context = pytest.importorskip("gather.context")
    item = pytest.importorskip("gather.item")
    store = pytest.importorskip("gather.store")
    needed = ("CorpusRootDescriptor", "CorpusRootIdentity",
              "inspect_corpus", "select_context")
    if not all(hasattr(context, name) for name in needed):
        pytest.skip("Gather descriptor API is unavailable")
    from harness.source_context_gather import GatherPathAdapter

    state = tmp_path / "state"
    corpus = state / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    replacement = corpus.with_name("replacement")
    store.Corpus(str(corpus), fsync=False).add([item.make_item(
        kind="document", id="alpha", title="Alpha",
        text="ORIGINAL-DESCRIPTOR-CANARY", source="docs",
        ref="original-ref", method="file-read", fetched_at=1.0)])
    store.Corpus(str(replacement), fsync=False).add([item.make_item(
        kind="document", id="beta", title="Beta",
        text="REPLACEMENT-DESCRIPTOR-CANARY", source="docs",
        ref="replacement-ref", method="file-read", fetched_at=1.0)])
    adapter = GatherPathAdapter()
    inspected = adapter.inspect(
        corpus, expected_identity=_identity_dict(corpus),
        expected_state_identity=_identity_dict(state), state_root=state,
        max_rows=2)
    row_ref = next(row["row_ref"] for row in inspected["rows"]
                   if row["id"] == "alpha")
    hidden = corpus.with_name("original-hidden")
    swapped = []

    def swap(_guard):
        try:
            corpus.rename(hidden)
            replacement.rename(corpus)
            swapped.append(True)
        except OSError:
            swapped.append(False)

    selected = adapter.select(
        corpus, [{"row_ref": row_ref, "start": 0, "limit": 26}],
        expected_corpus_digest=inspected["corpus_digest"],
        expected_identity=_identity_dict(corpus),
        expected_state_identity=_identity_dict(state), state_root=state,
        before_read=swap)

    text = selected["selections"][0]["text"]
    assert text == "ORIGINAL-DESCRIPTOR-CANARY"
    assert "REPLACEMENT-DESCRIPTOR-CANARY" not in text
    if os.name == "nt":
        assert swapped == [False]


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink store guard")
@pytest.mark.parametrize("folder", ("refs", "payloads", "projections", "bindings"))
def test_posix_store_refuses_symlinked_private_store_directories(
        tmp_path, folder):
    state = tmp_path / "state"
    state.mkdir()
    store = SourceContextStore(state, clock=lambda: "now")
    root_id = store.state_root_identity()
    attached = store.publish_selection(
        owner_ref=OWNER, state_root_identity=root_id,
        root_mode="flywheel_corpus", profile="demo", corpus_locator="tiny",
        corpus_root_identity=_identity_dict(state),
        gather_payload=_selection("POSIX-STORE-CANARY"), selected_at="now")
    base = state / "source-context" / "v1" / "owners" / OWNER
    original = base / folder
    outside = tmp_path / f"outside-{folder}"
    original.rename(outside)
    try:
        os.symlink(outside, original, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    with pytest.raises(SourceContextError) as exc:
        store.resolve_worker_payload(OWNER, (attached["source_context_ref"],))

    assert exc.value.code in {
        "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE",
        "SOURCE_CONTEXT_STORE_CORRUPT",
        "SOURCE_CONTEXT_AUTHORITY_BUSY",
    }


@pytest.mark.skipif(os.name == "nt", reason="WSL mounted-Windows boundary")
def test_source_context_refuses_wsl_mounted_windows_private_roots():
    from harness.private_artifact_fs import PrivateArtifactError
    from harness.private_artifact_fs_mount import admit_fd_mount, supported

    scratch = Path("/mnt/d/Temp")
    if not scratch.is_dir() or not supported():
        pytest.skip("mounted Windows filesystem is not available")
    fd = os.open(scratch, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))
    try:
        with pytest.raises(PrivateArtifactError) as raw_exc:
            admit_fd_mount(fd)
    finally:
        os.close(fd)
    if raw_exc.value.code != "UNSUPPORTED_FS":
        pytest.skip("mounted Windows filesystem is not refused here")
    state = scratch / f"source-context-mounted-windows-{os.getpid()}"
    state.mkdir(parents=True, exist_ok=False)
    try:
        with pytest.raises(SourceContextError) as exc:
            SourceContextStore(state).state_root_identity()
        assert exc.value.code == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    finally:
        state.rmdir()
