"""Adapter from Flywheel source-context routes to Gather descriptors."""
from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path

from .source_context_error import SourceContextError
from .source_context_identity import (
    artifact_identity, assert_supported_private_root, cap_identity_rows,
    identity_dict, source_error,
)

ADAPTER_VERSION = "gather.context.descriptor-api/v1"
PATH_ADAPTER_VERSION = "gather.context.path-api/v1"


class SourceContextArtifactGuard:
    """Hold a retained artifact root while exposing route identity rows."""

    guard_contract = "private-artifact-root-descriptor/v1"

    def __init__(self, path: Path, *, expected_identity: dict | None = None,
                 writable: bool = False) -> None:
        self.path, self.expected_identity = Path(path), expected_identity
        self.writable = writable
        self._cap = None
        self._rows: tuple[dict, ...] = ()
        self._identity: dict | None = None

    def __enter__(self):
        try:
            from .private_artifact_fs import open_artifact_root
            assert_supported_private_root(self.path)
            expected = (artifact_identity(self.expected_identity)
                        if self.expected_identity is not None else None)
            self._cap = open_artifact_root(
                self.path, expected=expected, writable=self.writable).__enter__()
            self._rows = cap_identity_rows(self._cap)
            self._identity = identity_dict(
                self.path, self._cap.identity, guarded_components=len(self._rows))
            return self
        except SourceContextError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise source_error(exc, read=True) from None

    def __exit__(self, *_args) -> bool:
        self.close()
        return False

    def close(self) -> None:
        cap, self._cap = self._cap, None
        if cap is not None:
            cap.close()

    def revalidate(self) -> None:
        if self._cap is None:
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
        if cap_identity_rows(self._cap) != self._rows:
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")

    def identity(self) -> dict:
        self.revalidate()
        return dict(self._identity)

    def identities(self) -> list[dict]:
        self.revalidate()
        return [dict(row) for row in self._rows]


class GatherPathAdapter:
    """Call Gather while Flywheel owns retained root authority."""

    adapter_version = ADAPTER_VERSION

    def __init__(self, *, inspect_fn=None, select_fn=None,
                 guard_cls=SourceContextArtifactGuard) -> None:
        self.inspect_fn, self.select_fn = inspect_fn, select_fn
        self.guard_cls = guard_cls
        self.last_identity: dict | None = None
        self.last_identities: tuple[dict, ...] = ()

    def inspect(self, path: Path, *, before_read=None, **caps) -> dict:
        expected = caps.pop("expected_identity", None)
        state_expected = caps.pop("expected_state_identity", None)
        state_root = caps.pop("state_root", None)
        if expected is None:
            return self._path_call("inspect", Path(path), before_read, (), caps)
        return self._descriptor_call(
            "inspect", Path(path), before_read, (), caps, expected,
            state_expected, state_root)

    def select(self, path: Path, selections: list, *,
               expected_corpus_digest: str, before_read=None, **caps) -> dict:
        expected = caps.pop("expected_identity", None)
        state_expected = caps.pop("expected_state_identity", None)
        state_root = caps.pop("state_root", None)
        args = (selections,)
        kw = dict(caps, expected_corpus_digest=expected_corpus_digest)
        if expected is None:
            return self._path_call("select", Path(path), before_read, args, kw)
        return self._descriptor_call(
            "select", Path(path), before_read, args, kw, expected,
            state_expected, state_root)

    def identity(self) -> dict:
        if self.last_identity is None:
            raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
        return dict(self.last_identity)

    def identities(self) -> list[dict]:
        return [dict(row) for row in self.last_identities]

    def _path_call(self, kind: str, path: Path, before_read, args, kwargs):
        fn = (self.inspect_fn if kind == "inspect" else self.select_fn) or _default(kind)
        with self.guard_cls(path) as guard:
            self._revalidate(guard)
            if before_read:
                before_read(guard)
            result = fn(path, *args, **kwargs)
            self._revalidate(guard)
            self.last_identity = guard.identity()
            self.last_identities = _identities(guard)
            self.adapter_version = PATH_ADAPTER_VERSION
            return result

    def _descriptor_call(self, kind: str, path: Path, before_read, args,
                         kwargs, expected, state_expected, state_root):
        explicit = self.inspect_fn if kind == "inspect" else self.select_fn
        fn, Identity, Descriptor = _descriptor_api(kind, explicit)
        try:
            from .private_artifact_fs import PrivateArtifactError, open_artifact_root
        except Exception as exc:
            raise source_error(exc, read=True) from None
        try:
            expected_id = artifact_identity(expected)
            with ExitStack() as stack:
                if state_root is not None and state_expected is not None:
                    assert_supported_private_root(Path(state_root))
                    stack.enter_context(open_artifact_root(
                        state_root, expected=artifact_identity(state_expected),
                        writable=False))
                assert_supported_private_root(path)
                cap = stack.enter_context(open_artifact_root(
                    path, expected=expected_id, writable=False))
                rows = cap_identity_rows(cap)
                self.last_identity = identity_dict(
                    path, cap.identity, guarded_components=len(rows))
                self.last_identities = rows
                if before_read:
                    before_read(self)
                with cap.borrow_descriptor() as borrowed:
                    gid = Identity(
                        platform=borrowed.identity.platform,
                        device=borrowed.identity.device,
                        inode=borrowed.identity.inode)
                    descriptor = Descriptor(
                        expected_identity=gid, fd=borrowed.fd,
                        handle=borrowed.handle)
                    result = fn(descriptor, *args, **kwargs)
                self.last_identity = identity_dict(
                    path, cap.identity, guarded_components=len(rows))
                self.last_identities = rows
                self.adapter_version = ADAPTER_VERSION
                return result
        except SourceContextError:
            raise
        except PrivateArtifactError as exc:
            raise source_error(exc, read=True) from None

    @staticmethod
    def _revalidate(guard) -> None:
        check = getattr(guard, "revalidate", None)
        if callable(check):
            check()


def _default(kind: str):
    return _descriptor_api(kind)[0]


def _descriptor_api(kind: str, explicit=None):
    try:
        from gather.context import (
            CorpusRootDescriptor, CorpusRootIdentity, inspect_corpus,
            select_context,
        )
    except Exception:
        if explicit is not None:
            raise SourceContextError("SOURCE_CONTEXT_GATHER_UNAVAILABLE") from None
        raise SourceContextError("SOURCE_CONTEXT_GATHER_UNAVAILABLE") from None
    fn = explicit if explicit is not None else (
        inspect_corpus if kind == "inspect" else select_context)
    return fn, CorpusRootIdentity, CorpusRootDescriptor


def _identities(guard) -> tuple[dict, ...]:
    read = getattr(guard, "identities", None)
    return tuple(read()) if callable(read) else ()
