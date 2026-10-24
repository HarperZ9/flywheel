import hashlib
import json
from pathlib import Path
import sys

import pytest

from harness.evidence_json import canonical_bytes
from harness.runtime_descriptor import (
    RUNTIME_SCOPE, RUNTIME_SCOPE_V1, SCHEMA_V1, pytest_runtime_descriptor,
    validate_runtime_descriptor)
from harness.scope import LEGACY_SCOPE_KEY


def test_pytest_runtime_descriptor_is_reproducible_and_public_safe():
    first = pytest_runtime_descriptor(); second = pytest_runtime_descriptor()
    assert first == second
    assert set(first) == {"schema", "python", "pytest", "scope"}
    assert first["schema"] == "flywheel.pytest-runtime/v2"
    assert set(first["python"]) == {
        "implementation", "version", "cache_tag", "abi_flags", "byteorder", "platform"}
    pytest_id = first["pytest"]
    assert set(pytest_id) == {
        "distribution", "version", "requires_dist", "source", "identity_sha256"}
    assert pytest_id["distribution"] == "pytest" and pytest_id["version"]
    source = pytest_id["source"]
    assert source["file_count"] == len(source["files"]) > 0
    assert source["bytes"] == sum(item["bytes"] for item in source["files"])
    expected = "sha256:" + hashlib.sha256(canonical_bytes(source["files"])).hexdigest()
    assert source["manifest_sha256"] == expected
    identity = {key: pytest_id[key] for key in (
        "distribution", "version", "requires_dist", "source")}
    assert pytest_id["identity_sha256"] == (
        "sha256:" + hashlib.sha256(canonical_bytes(identity)).hexdigest())
    blob = json.dumps(first, sort_keys=True).lower()
    assert str(Path(sys.executable).parent).lower() not in blob
    assert str(Path.cwd()).lower() not in blob and "location" not in blob


def test_runtime_descriptor_validator_rejects_a_coherent_identity_mutation():
    descriptor = pytest_runtime_descriptor()
    descriptor["pytest"]["version"] = "0.0-tampered"
    with pytest.raises(ValueError, match="runtime|descriptor|identity"):
        validate_runtime_descriptor(descriptor)


def test_runtime_descriptor_states_the_unbound_closure_exactly():
    descriptor = pytest_runtime_descriptor()
    assert descriptor["scope"] == list(RUNTIME_SCOPE)
    assert any("RUNTIME_IDENTITY_BOUND" in item for item in RUNTIME_SCOPE)
    assert any("MATCHING_RUNTIME_REPRODUCTION" in item for item in RUNTIME_SCOPE)


def test_v1_descriptor_still_validates_and_mixed_names_fail():
    descriptor = pytest_runtime_descriptor()
    old = {k: v for k, v in descriptor.items() if k != "scope"}
    old.update({"schema": SCHEMA_V1, LEGACY_SCOPE_KEY: list(RUNTIME_SCOPE_V1)})
    validate_runtime_descriptor(old)
    mixed = dict(old)
    mixed["scope"] = mixed.pop(LEGACY_SCOPE_KEY)
    with pytest.raises(ValueError):
        validate_runtime_descriptor(mixed)
