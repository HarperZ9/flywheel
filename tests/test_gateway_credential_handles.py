import json

import pytest

from harness.credential_handle_route import (
    credential_handle_get, credential_handle_post,
)
from harness.credential_handles import CredentialHandleError, CredentialHandleStore


OWNER = "owner_" + "a" * 32
OTHER = "owner_" + "b" * 32
SECRET = "synthetic-value-never-persisted"


def _store(root, slots, *, token="a" * 32):
    return CredentialHandleStore(
        root, keychain_get=lambda name: slots.get(name),
        token_hex=lambda _size: token)


def test_bind_persists_only_owner_metadata_and_resolves_exactly(tmp_path):
    store = _store(tmp_path, {"EXAMPLE_API_KEY": SECRET})
    handle = store.bind(OWNER, "EXAMPLE_API_KEY")
    assert handle.credential_ref == "cred_" + "a" * 32
    dumped = b"".join(path.read_bytes() for path in tmp_path.rglob("*.json"))
    assert SECRET.encode() not in dumped
    bindings = store.resolve_exact(
        OWNER, [handle.credential_ref], ["EXAMPLE_API_KEY"])
    assert repr(bindings) == "CredentialBindings(<redacted>)"
    assert bindings.value_for("EXAMPLE_API_KEY") == SECRET


def test_wrong_owner_missing_extra_and_ambient_slots_fail_closed(tmp_path):
    store = _store(tmp_path, {"EXAMPLE_API_KEY": SECRET})
    ref = store.bind(OWNER, "EXAMPLE_API_KEY").credential_ref
    for owner, refs, required in [
        (OTHER, [ref], ["EXAMPLE_API_KEY"]),
        (OWNER, [], ["EXAMPLE_API_KEY"]),
        (OWNER, [ref], []),
        (OWNER, ["cred_" + "b" * 32], ["EXAMPLE_API_KEY"]),
    ]:
        with pytest.raises(CredentialHandleError) as failure:
            store.resolve_exact(owner, refs, required)
        assert failure.value.code == "PERMISSION_REQUIRED"
        assert SECRET not in str(failure.value)


def test_empty_exact_resolution_needs_no_store_or_keychain(tmp_path):
    calls = []
    store = CredentialHandleStore(
        tmp_path, keychain_get=lambda name: calls.append(name) or SECRET)
    assert store.slot_names_exact(OWNER, []) == ()
    assert repr(store.resolve_exact(OWNER, [], [])) == (
        "CredentialBindings(<redacted>)")
    assert calls == []
    assert not (tmp_path / "credential-handles").exists()


def test_missing_slot_after_binding_burns_no_value_into_error(tmp_path):
    slots = {"EXAMPLE_API_KEY": SECRET}
    store = _store(tmp_path, slots)
    ref = store.bind(OWNER, "EXAMPLE_API_KEY").credential_ref
    slots.clear()
    with pytest.raises(CredentialHandleError) as failure:
        store.resolve_exact(OWNER, [ref], ["EXAMPLE_API_KEY"])
    assert failure.value.code == "PERMISSION_REQUIRED"
    assert SECRET not in str(failure.value)


def test_keychain_failure_is_replaced_with_fixed_non_echoing_error(tmp_path):
    failing = [False]

    def keychain_get(_name):
        if failing[0]:
            raise RuntimeError(SECRET)
        return SECRET

    store = CredentialHandleStore(
        tmp_path, keychain_get=keychain_get,
        token_hex=lambda _size: "a" * 32)
    ref = store.bind(OWNER, "EXAMPLE_API_KEY").credential_ref
    failing[0] = True
    with pytest.raises(CredentialHandleError) as failure:
        store.resolve_exact(OWNER, [ref], ["EXAMPLE_API_KEY"])
    assert failure.value.code == "PERMISSION_REQUIRED"
    assert SECRET not in str(failure.value)


def test_metadata_mismatch_fails_before_keychain_resolution(tmp_path):
    calls = []
    store = CredentialHandleStore(
        tmp_path, keychain_get=lambda name: calls.append(name) or SECRET,
        token_hex=lambda _size: "a" * 32)
    ref = store.bind(OWNER, "EXAMPLE_API_KEY").credential_ref
    calls.clear()
    with pytest.raises(CredentialHandleError):
        store.resolve_exact(OWNER, [ref], ["OTHER_API_KEY"])
    assert calls == []


def test_slot_names_exact_reads_metadata_without_keychain_access(tmp_path):
    calls = []
    store = CredentialHandleStore(
        tmp_path, keychain_get=lambda name: calls.append(name) or SECRET,
        token_hex=lambda _size: "a" * 32)
    ref = store.bind(OWNER, "EXAMPLE_API_KEY").credential_ref
    calls.clear()
    assert store.slot_names_exact(OWNER, [ref]) == ("EXAMPLE_API_KEY",)
    assert calls == []


def test_missing_slot_bind_does_not_create_handle_storage(tmp_path):
    store = _store(tmp_path, {})
    with pytest.raises(CredentialHandleError) as failure:
        store.bind(OWNER, "EXAMPLE_API_KEY")
    assert failure.value.code == "PERMISSION_REQUIRED"
    assert not (tmp_path / "credential-handles").exists()


def test_private_routes_return_refs_and_safe_labels_only(tmp_path):
    slots = {"EXAMPLE_API_KEY": SECRET}
    post, status = credential_handle_post(
        "/api/credential-handles/bind",
        json.dumps({"schema": "flywheel.credential-handle-bind/v1",
                    "credential_name": "EXAMPLE_API_KEY"}).encode(),
        owner_ref=OWNER, state_root=tmp_path,
        keychain_get=lambda name: slots.get(name), token_hex=lambda _: "a" * 32)
    assert status == 200 and post["credential_ref"].startswith("cred_")
    listed, list_status = credential_handle_get(
        "/api/credential-handles", owner_ref=OWNER, state_root=tmp_path)
    assert list_status == 200 and listed["handles"] == [{
        "credential_ref": post["credential_ref"],
        "credential_name": "EXAMPLE_API_KEY",
    }]
    assert SECRET not in json.dumps([post, listed])


def test_authorized_child_environment_is_allowlisted_and_exact(tmp_path):
    store = _store(tmp_path, {"EXAMPLE_API_KEY": SECRET})
    ref = store.bind(OWNER, "EXAMPLE_API_KEY").credential_ref
    bindings = store.resolve_exact(OWNER, [ref], ["EXAMPLE_API_KEY"])
    env = bindings.child_environment({
        "PATH": "safe-path", "HOME": "safe-home", "HTTP_PROXY": "ambient",
        "GIT_TOKEN": "ambient-secret", "EXAMPLE_API_KEY": "ambient-wrong",
    }, platform="posix")
    assert env == {"PATH": "safe-path", "HOME": "safe-home",
                   "EXAMPLE_API_KEY": SECRET}


def test_windows_child_environment_has_no_unlisted_ambient_values(tmp_path):
    store = _store(tmp_path, {"EXAMPLE_API_KEY": SECRET})
    ref = store.bind(OWNER, "EXAMPLE_API_KEY").credential_ref
    bindings = store.resolve_exact(OWNER, [ref], ["EXAMPLE_API_KEY"])
    env = bindings.child_environment({
        "PATH": "path", "PATHEXT": ".EXE", "SYSTEMROOT": "root",
        "WINDIR": "windows", "COMSPEC": "cmd", "TEMP": "temp",
        "TMP": "tmp", "HTTP_PROXY": "ambient", "SSH_AUTH_SOCK": "ambient",
    }, platform="windows")
    assert env == {
        "PATH": "path", "PATHEXT": ".EXE", "SYSTEMROOT": "root",
        "WINDIR": "windows", "COMSPEC": "cmd", "TEMP": "temp",
        "TMP": "tmp", "EXAMPLE_API_KEY": SECRET,
    }
