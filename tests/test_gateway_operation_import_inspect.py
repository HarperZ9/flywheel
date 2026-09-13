import pytest

from harness.gateway_operation import GatewayOperationError, canonicalize_operation


SHA = "0123456789abcdef" * 4


def _operation(**changes):
    op = {
        "source": {
            "kind": "client-upload",
            "format": "inspect-json",
            "sha256": SHA,
            "byte_length": 123,
            "filename": "run.json",
        },
        "data_refs": [f"data_inspect.source:{SHA[:32]}"],
        "credential_refs": [],
    }
    for key, value in changes.items():
        if key.startswith("source_"):
            op["source"][key[7:]] = value
        else:
            op[key] = value
    return op


def test_import_inspect_operation_derives_destination_scope_and_data_ref():
    canonical = canonicalize_operation("import.inspect", _operation())

    assert canonical.destination == {"kind": "import", "ref": f"inspect-json:{SHA[:16]}"}
    assert canonical.scopes == ("write",)
    assert canonical.data_refs == (f"data_inspect.source:{SHA[:32]}",)
    assert canonical.credential_refs == ()


@pytest.mark.parametrize("change", [
    {"source_kind": "server-path"},
    {"source_format": "zip"},
    {"source_sha256": SHA.upper()},
    {"source_byte_length": 0},
    {"source_byte_length": 16 * 1024 * 1024 + 1},
    {"source_filename": "../run.json"},
    {"data_refs": []},
    {"data_refs": [f"data_inspect.source:{SHA[:31]}x"]},
    {"credential_refs": ["cred_" + "a" * 32]},
])
def test_import_inspect_operation_rejects_non_exact_metadata(change):
    with pytest.raises(GatewayOperationError) as failure:
        canonicalize_operation("import.inspect", _operation(**change))

    assert failure.value.code == "INVALID_REQUEST"
