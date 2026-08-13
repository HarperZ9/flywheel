"""Closed checker source/runtime identity carried by an evidence packet."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from .evidence_json import canonical_bytes, strict_load_json
from .runtime_descriptor import validate_runtime_descriptor

SCHEMA = "flywheel.checker-source-set/v2"
MAX_SOURCE = 1_048_576
PYTEST_MODULES = (
    "harness.execution_input_protection",
    "harness.oracle",
    "harness.pytest_prepared",
    "harness.pytest_provenance",
    "harness.runtime_descriptor",
    "harness.windows_low_integrity",
)


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def runtime_digest(runtime: dict) -> str:
    validate_runtime_descriptor(runtime)
    return _digest(canonical_bytes(runtime))


def _path(module: str) -> Path:
    if module.startswith("harness.") and module.count(".") == 1:
        path = Path(__file__).with_name(module.split(".")[1] + ".py")
    else:
        path = Path(getattr(sys.modules.get(module), "__file__", ""))
    if not path.is_file() or path.suffix != ".py":
        raise ValueError(f"checker source is unavailable for {module!r}")
    return path


def _read(module: str) -> bytes:
    with _path(module).open("rb") as stream:
        data = stream.read(MAX_SOURCE + 1)
    if len(data) > MAX_SOURCE:
        raise ValueError("checker source exceeds byte limit")
    data.decode("utf-8", "strict")
    return data


def checker_source(oracle, runtime: dict | None = None) -> tuple[str, bytes, str | None]:
    """Return the primary module, closed source set, and runtime digest."""
    module = type(oracle).__module__
    names = PYTEST_MODULES if oracle.oracle_type == "pytest" else (module,)
    if oracle.oracle_type == "pytest":
        if runtime is None:
            raise ValueError("pytest checker identity requires a runtime descriptor")
        runtime_sha = runtime_digest(runtime)
    elif runtime is not None:
        raise ValueError("non-pytest checker identity cannot assert a pytest runtime")
    else:
        runtime_sha = None
    sources = []
    for name in names:
        data = _read(name)
        sources.append({"module": name, "sha256": _digest(data),
                        "source": data.decode("utf-8")})
    carried = {"schema": SCHEMA, "runtime": runtime,
               "runtime_descriptor_sha256": runtime_sha, "sources": sources}
    return module, canonical_bytes(carried), runtime_sha


def validate_checker_source(blob: bytes, *, checker_module: str,
                            oracle_type: str, runtime: dict | None) -> dict:
    """Rehash a carried source set without consulting the verifier host."""
    value = strict_load_json(blob, max_depth=32)
    if type(value) is not dict or set(value) != {
            "schema", "runtime", "runtime_descriptor_sha256", "sources"}:
        raise ValueError("checker source set is not closed")
    if value["schema"] != SCHEMA or value["runtime"] != runtime:
        raise ValueError("checker source runtime drift")
    expected_runtime = runtime_digest(runtime) if oracle_type == "pytest" else None
    if value["runtime_descriptor_sha256"] != expected_runtime:
        raise ValueError("checker runtime digest drift")
    expected_names = list(PYTEST_MODULES if oracle_type == "pytest" else (checker_module,))
    sources = value["sources"]
    if type(sources) is not list or [item.get("module") for item in sources
                                    if type(item) is dict] != expected_names:
        raise ValueError("checker source module set drift")
    for item in sources:
        if type(item) is not dict or set(item) != {"module", "sha256", "source"}:
            raise ValueError("checker source entry is not closed")
        if type(item["source"]) is not str or len(item["source"].encode()) > MAX_SOURCE:
            raise ValueError("checker source entry is malformed")
        if item["sha256"] != _digest(item["source"].encode("utf-8")):
            raise ValueError("checker source entry digest drift")
    return value
