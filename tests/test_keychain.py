"""The keychain must hold the secret and never show it: a stored value
round-trips through resolution, the environment wins over the store,
presence surfaces never contain values, and deleting a missing entry is a
named error. Skips honestly where no OS store exists."""

import os
import sys

import pytest

from harness import keychain

pytestmark = pytest.mark.skipif(sys.platform != "win32",
                                reason="no supported OS credential store")

_NAME = "FLYWHEEL_TEST_KEY_XYZ"


@pytest.fixture(autouse=True)
def _clean():
    keychain.keychain_delete(_NAME)
    os.environ.pop(_NAME, None)
    yield
    keychain.keychain_delete(_NAME)
    os.environ.pop(_NAME, None)


def test_set_resolve_delete_roundtrip():
    assert keychain.keychain_set(_NAME, "s3cret-value")["stored"] == _NAME
    assert keychain.resolve_credential(_NAME) == "s3cret-value"
    assert keychain.credential_source(_NAME) == "keychain"
    assert keychain.keychain_delete(_NAME)["deleted"] == _NAME
    assert keychain.resolve_credential(_NAME) == ""
    assert keychain.credential_source(_NAME) == "absent"


def test_environment_wins_over_the_store():
    keychain.keychain_set(_NAME, "from-keychain")
    os.environ[_NAME] = "from-env"
    assert keychain.resolve_credential(_NAME) == "from-env"
    assert keychain.credential_source(_NAME) == "env"


def test_presence_surfaces_never_carry_the_value():
    keychain.keychain_set(_NAME, "s3cret-value")
    src = keychain.credential_source(_NAME)
    assert "s3cret" not in src
    from harness.endpoint_registry import _credential
    assert _credential(_NAME, local=False) == "present"


def test_delete_missing_is_a_named_error():
    out = keychain.keychain_delete(_NAME)
    assert "error" in out and _NAME in out["error"]


def test_empty_inputs_refused():
    assert "error" in keychain.keychain_set("", "x")
    assert "error" in keychain.keychain_set(_NAME, "")
    assert keychain.resolve_credential("") == ""
