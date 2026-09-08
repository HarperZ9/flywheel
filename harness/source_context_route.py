"""Authenticated source-context inspect/select/attach route."""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
import re

from .evidence_json import canonical_sha256
from .evidence_public import TransportError, error_response, exact_request, parse_json
from .source_context_gather import GatherPathAdapter
from .source_context_store import (
    SourceContextError, SourceContextStore, _json_file, _owner, _write_once,
)

REQUEST_SCHEMA = "flywheel.source-context-request/v1"
ADMISSION_SCHEMA = "flywheel.source-context-corpus-admission/v1"
_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_INSPECT_CAPS = frozenset(("max_rows", "excerpt_chars", "max_catalog_bytes",
    "max_catalog_rows", "max_body_bytes", "max_read_bytes"))
_SELECT_CAPS = frozenset(("max_rows", "max_total_chars", "default_limit",
    "max_catalog_bytes", "max_catalog_rows", "max_body_bytes", "max_read_bytes"))
_CAP_LIMITS = {"max_rows": 50, "excerpt_chars": 100_000,
    "max_total_chars": 100_000, "default_limit": 100_000,
    "max_catalog_bytes": 100_000_000, "max_catalog_rows": 100_000,
    "max_body_bytes": 100_000_000, "max_read_bytes": 100_000_000}


def admit_flywheel_corpus(state_root: Path, owner_ref: str, profile: str,
                          corpus: str, *, guard_cls=None, clock=None) -> dict:
    """Persist one owner-bound corpus locator admitted by live guard identity."""
    state_root, owner, profile = Path(state_root), _owner(owner_ref), _safe_name(profile)
    parts = _corpus_parts(corpus)
    root = state_root / "source-context" / "corpora" / owner / profile
    candidate = root.joinpath(*parts)
    if not candidate.is_dir() or not _contained(root, candidate):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    if guard_cls is None:
        guard_cls = _default_guard()
    with guard_cls(candidate) as guard:
        read = getattr(guard, "identities", None)
        ids = _identity_bundle(state_root, guard.identity(),
            tuple(read()) if callable(read) else (), None)
    record = {"schema": ADMISSION_SCHEMA, "owner_ref": owner,
        "root_mode": "flywheel_corpus", "profile": profile,
        "corpus": "/".join(parts),
        "corpus_locator_sha256": _plain_text_sha("/".join(parts)),
        "state_root_identity": ids["state_root_identity"],
        "corpus_root_identity": ids["corpus_root_identity"],
        "canonical_volume_root_identity": ids["component_identities"][0],
        "component_identities": list(ids["component_identities"]),
        "guard_contract": "windows-directory-read-share-only/v1"}
    _write_once(_admission_path(state_root, owner, profile, corpus), record)
    return record


def source_context_post(path: str, raw: bytes, *, owner_ref: str,
                        state_root: Path, clock, gather=None,
                        guard_cls=None) -> tuple[dict, int]:
    try:
        action = path.rstrip("/").rsplit("/", 1)[-1]
        if action not in {"inspect", "select", "attach"}:
            raise TransportError("NOT_FOUND", "source-context route not found", 404)
        req = parse_json(raw)
        expected = {"schema", "root_mode", "profile", "corpus"}
        cap_names = _INSPECT_CAPS if action == "inspect" else _SELECT_CAPS
        optional = cap_names if action == "inspect" else cap_names | {"expected_corpus_digest", "selections"}
        exact_request(req, expected | optional, optional=optional)
        if req["schema"] != REQUEST_SCHEMA:
            raise SourceContextError("INVALID_REQUEST")
        caps = _caps(req, cap_names)
        corpus, admission = _corpus_admission(
            Path(state_root), owner_ref, req["root_mode"], req["profile"], req["corpus"])
        if action == "inspect":
            return _inspect(corpus, caps, gather, guard_cls, state_root, admission)
        if ("expected_corpus_digest" not in req or "selections" not in req
                or _HEX64.fullmatch(req["expected_corpus_digest"]) is None
                or type(req["selections"]) is not list):
            raise SourceContextError("INVALID_REQUEST")
        selected, ids = _select(corpus, req["selections"], req["expected_corpus_digest"],
            caps, gather, guard_cls, state_root, admission)
        if action == "select":
            return dict(selected, corpus_root_identity=ids["corpus_root_identity"]), 200
        attached = SourceContextStore(state_root, clock=clock).publish_selection(
            owner_ref=owner_ref, state_root_identity=ids["state_root_identity"],
            root_mode=req["root_mode"], profile=req["profile"],
            corpus_locator=req["corpus"], corpus_root_identity=ids["corpus_root_identity"],
            gather_payload=selected, selected_at=clock())
        return attached, 200
    except TransportError as exc:
        return error_response(exc)
    except SourceContextError as exc:
        return _source_error(exc)
    except Exception:
        return _source_error(SourceContextError("SOURCE_CONTEXT_SELECTION_FAILED"))


def _inspect(corpus: Path, caps: dict, gather, guard_cls,
             state_root: Path, admission: dict) -> tuple[dict, int]:
    result, ids = _guarded_call(corpus, gather, guard_cls, "inspect",
        caps=caps, state_root=state_root, admission=admission)
    return dict(result, adapter_version="gather.context.path-api/v1",
        corpus_root_identity=ids["corpus_root_identity"]), 200


def _select(corpus: Path, selections: list, digest: str, caps: dict,
            gather, guard_cls, state_root: Path, admission: dict) -> tuple[dict, dict]:
    return _guarded_call(corpus, gather, guard_cls, "select",
        selections=selections, expected_corpus_digest=digest, caps=caps,
        state_root=state_root, admission=admission)


def _guarded_call(corpus: Path, gather, guard_cls, action: str, **kwargs):
    if gather is None:
        adapter = GatherPathAdapter(guard_cls=guard_cls or _default_guard())
        result = getattr(adapter, action)(corpus, **_flatten(kwargs))
        return result, _identity_bundle(kwargs.get("state_root"),
            adapter.last_identity, getattr(adapter, "last_identities", ()),
            kwargs.get("admission"))
    if guard_cls is None:
        guard_cls = _default_guard()
    with guard_cls(corpus) as guard:
        _revalidate(guard)
        if action == "inspect":
            result = gather.inspect(corpus, **kwargs["caps"])
        else:
            result = gather.select(corpus, kwargs["selections"],
                expected_corpus_digest=kwargs["expected_corpus_digest"],
                **kwargs["caps"])
        _revalidate(guard)
        read = getattr(guard, "identities", None)
        return result, _identity_bundle(kwargs.get("state_root"), guard.identity(),
            tuple(read()) if callable(read) else (), kwargs.get("admission"))


def _flatten(kwargs: dict) -> dict:
    caps = kwargs.get("caps", {})
    return {key: value for key, value in kwargs.items()
            if key not in {"caps", "state_root", "admission"}} | caps


def _default_guard():
    from .source_context_windows import SourceContextWindowsGuard
    return SourceContextWindowsGuard


def _revalidate(guard) -> None:
    check = getattr(guard, "revalidate", None)
    if callable(check):
        check()


def _corpus_admission(state_root: Path, owner_ref: str, root_mode: object,
                      profile: object, corpus: object) -> tuple[Path, dict]:
    if root_mode != "flywheel_corpus":
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    owner, profile = _owner(owner_ref), _safe_name(profile)
    parts = _corpus_parts(corpus)
    admission = _read_admission(state_root, owner, profile, "/".join(parts))
    root = Path(state_root) / "source-context" / "corpora" / owner / profile
    candidate = root.joinpath(*parts)
    if not candidate.is_dir() or not _contained(root, candidate):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    return candidate, admission


def _read_admission(state_root: Path, owner: str, profile: str, corpus: str) -> dict:
    path = _admission_path(state_root, owner, profile, corpus)
    if not path.exists():
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    value = _json_file(path)
    components = value.get("component_identities")
    if type(components) is not list or not components:
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    expected_corpus = dict(components[-1], guarded_components=len(components))
    if (value.get("schema") != ADMISSION_SCHEMA or value.get("owner_ref") != owner
            or value.get("root_mode") != "flywheel_corpus"
            or value.get("profile") != profile or value.get("corpus") != corpus
            or value.get("corpus_locator_sha256") != _plain_text_sha(corpus)
            or value.get("canonical_volume_root_identity") != components[0]
            or value.get("corpus_root_identity") != expected_corpus
            or value.get("state_root_identity", {}).get("path_sha256") != _plain_path_sha(state_root)):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    return value


def _admission_path(state_root: Path, owner: str, profile: str, corpus: str) -> Path:
    return (Path(state_root) / "source-context" / "admissions" / "v1" / "owners"
            / owner / profile / f"{_plain_text_sha(corpus)}.json")


def _corpus_parts(value: object) -> list[str]:
    if type(value) is not str or not value:
        raise SourceContextError("INVALID_REQUEST")
    raw = value.replace("\\", "/").split("/")
    if not raw or any(part in ("", ".", "..") for part in raw):
        raise SourceContextError("INVALID_REQUEST")
    return [_safe_name(part) for part in raw]


def _safe_name(value: object) -> str:
    if type(value) is not str or _SAFE.fullmatch(value) is None:
        raise SourceContextError("INVALID_REQUEST")
    return value


def _contained(root: Path, candidate: Path) -> bool:
    try:
        root_name = os.path.normcase(str(root.resolve(strict=True)))
        cand_name = os.path.normcase(str(candidate.resolve(strict=True)))
        return os.path.commonpath((root_name, cand_name)) == root_name
    except (OSError, RuntimeError, ValueError):
        return False


def _state_identity(path: Path) -> dict:
    try:
        stat = Path(path).stat()
        return {"platform": os.name, "path_sha256": canonical_sha256(
            {"path": os.path.normcase(str(Path(path).absolute()))}),
            "mtime_ns": int(stat.st_mtime_ns), "inode": int(stat.st_ino)}
    except OSError:
        return {"platform": os.name, "path_sha256": canonical_sha256(
            {"path": os.path.normcase(str(Path(path).absolute()))})}


def _identity_bundle(state_root: Path | None, final: dict | None,
                     identities: tuple[dict, ...], admission: dict | None) -> dict:
    if state_root is None or final is None:
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    state = next((item for item in identities
                  if item.get("path_sha256") == _plain_path_sha(state_root)), None)
    if state is None:
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")
    bundle = {"state_root_identity": dict(state), "corpus_root_identity": dict(final),
              "component_identities": tuple(dict(item) for item in identities)}
    if admission is not None:
        _validate_admission_identity(bundle, admission)
    return bundle


def _validate_admission_identity(bundle: dict, admission: dict) -> None:
    if (bundle["state_root_identity"] != admission.get("state_root_identity")
            or bundle["corpus_root_identity"] != admission.get("corpus_root_identity")
            or list(bundle["component_identities"]) != admission.get("component_identities")):
        raise SourceContextError("SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE")


def _plain_path_sha(path: Path) -> str:
    text = os.path.normcase(os.path.abspath(str(Path(path))))
    return hashlib.sha256(text.encode("utf-8", "strict")).hexdigest()


def _plain_text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _caps(req: dict, names) -> dict:
    caps = {}
    for key in names:
        if key in req:
            value = req[key]
            if type(value) is not int or value < 1 or value > _CAP_LIMITS[key]:
                raise SourceContextError("INVALID_REQUEST")
            caps[key] = value
    return caps


def _source_error(exc: SourceContextError) -> tuple[dict, int]:
    status = {"SOURCE_CONTEXT_PERMISSION_DENIED": 403,
        "SOURCE_CONTEXT_AUTHORITY_BUSY": 503,
        "SOURCE_CONTEXT_GATHER_UNAVAILABLE": 503,
        "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE": 409,
        "SOURCE_CONTEXT_DURABILITY_UNAVAILABLE": 409,
        "SOURCE_CONTEXT_REF_COLLISION": 409,
        "SOURCE_CONTEXT_REF_NOT_FOUND": 404,
        "SOURCE_CONTEXT_SELECTION_FAILED": 409,
        "SOURCE_CONTEXT_STORE_CORRUPT": 409,
        "INVALID_REQUEST": 422}.get(exc.code, 500)
    messages = {"SOURCE_CONTEXT_PERMISSION_DENIED":
        "source context is not available to this owner",
        "SOURCE_CONTEXT_AUTHORITY_BUSY": "source context authority is busy",
        "SOURCE_CONTEXT_GATHER_UNAVAILABLE": "source context selection is unavailable",
        "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE": "source context authority is unavailable",
        "SOURCE_CONTEXT_DURABILITY_UNAVAILABLE": "source context durability is unavailable",
        "SOURCE_CONTEXT_REF_COLLISION": "source context reference collision",
        "SOURCE_CONTEXT_REF_NOT_FOUND": "source context reference was not found",
        "SOURCE_CONTEXT_SELECTION_FAILED": "source context selection failed",
        "SOURCE_CONTEXT_STORE_CORRUPT": "source context snapshot is invalid",
        "INVALID_REQUEST": "source-context request is invalid"}
    return error_response(TransportError(exc.code,
        messages.get(exc.code, "source context store is invalid"), status))
