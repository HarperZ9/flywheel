from __future__ import annotations

def test_gateway_keychain_set_rejects_bulletin_slot(monkeypatch) -> None:
    from harness import gateway, keychain
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME

    body: dict = {}
    calls: list[tuple[str, str]] = []

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        gateway._Handler,
        "_req_json",
        lambda _handler: ({"name": BULLETIN_CREDENTIAL_NAME, "value": "invalid"}, None),
    )
    monkeypatch.setattr(
        keychain,
        "keychain_set",
        lambda name, value: calls.append((name, value)) or {"stored": name},
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain/set"
    handler.command = "POST"

    handler._post()

    assert body["code"] == 400
    assert body["obj"]["error"]["code"] == "USE_BULLETIN_IDENTITY"
    assert calls == []


def test_gateway_keychain_set_rejects_case_alias_bulletin_slot(monkeypatch) -> None:
    from harness import gateway, keychain

    body: dict = {}
    calls: list[tuple[str, str]] = []

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        gateway._Handler,
        "_req_json",
        lambda _handler: ({"name": "bulletin_agent_jwk", "value": "invalid"}, None),
    )
    monkeypatch.setattr(
        keychain,
        "keychain_set",
        lambda name, value: calls.append((name, value)) or {"stored": name},
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain/set"
    handler.command = "POST"

    handler._post()

    assert body["code"] == 400
    assert body["obj"]["error"]["code"] == "USE_BULLETIN_IDENTITY"
    assert calls == []


def test_gateway_keychain_set_rejects_nul_suffixed_bulletin_slot(monkeypatch) -> None:
    from harness import gateway, keychain
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME

    body: dict = {}
    calls: list[tuple[str, str]] = []

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        gateway._Handler,
        "_req_json",
        lambda _handler: (
            {"name": f"{BULLETIN_CREDENTIAL_NAME}\x00suffix", "value": "synthetic"},
            None,
        ),
    )
    monkeypatch.setattr(
        keychain,
        "keychain_set",
        lambda name, value: calls.append((name, value)) or {"stored": name},
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain/set"
    handler.command = "POST"

    handler._post()

    assert body["code"] == 400
    assert body["obj"]["error"]["code"] == "INVALID_KEYCHAIN_NAME"
    assert calls == []


def test_gateway_keychain_set_keeps_normal_roster_key_compatibility(monkeypatch) -> None:
    from harness import gateway, keychain

    body: dict = {}
    calls: list[tuple[str, str]] = []

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        gateway._Handler,
        "_req_json",
        lambda _handler: ({"name": "OPENAI_API_KEY", "value": "synthetic"}, None),
    )
    monkeypatch.setattr(
        keychain,
        "keychain_set",
        lambda name, value: calls.append((name, value)) or {"stored": name},
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain/set"
    handler.command = "POST"

    handler._post()

    assert body["code"] == 200
    assert body["obj"] == {"stored": "OPENAI_API_KEY"}
    assert calls == [("OPENAI_API_KEY", "synthetic")]


def test_gateway_keychain_set_preserves_non_bulletin_name_case(monkeypatch) -> None:
    from harness import gateway, keychain

    body: dict = {}
    calls: list[tuple[str, str]] = []

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        gateway._Handler,
        "_req_json",
        lambda _handler: ({"name": "OpenAI_API_Key", "value": "synthetic"}, None),
    )
    monkeypatch.setattr(
        keychain,
        "keychain_set",
        lambda name, value: calls.append((name, value)) or {"stored": name},
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain/set"
    handler.command = "POST"

    handler._post()

    assert body["code"] == 200
    assert body["obj"] == {"stored": "OpenAI_API_Key"}
    assert calls == [("OpenAI_API_Key", "synthetic")]


def test_gateway_keychain_delete_for_bulletin_slot_uses_identity_store(monkeypatch, tmp_path) -> None:
    from harness import gateway, keychain
    from harness import bulletin_identity_store
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME

    body: dict = {}
    locked_calls: list[object] = []
    generic_calls: list[str] = []

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        gateway._Handler,
        "_req_json",
        lambda _handler: ({"name": BULLETIN_CREDENTIAL_NAME}, None),
    )
    monkeypatch.setattr(
        bulletin_identity_store,
        "delete_identity_keychain_slot",
        lambda **kwargs: locked_calls.append(kwargs.get("keychain_lock_root")) or {"deleted": BULLETIN_CREDENTIAL_NAME},
    )
    monkeypatch.setattr(
        keychain,
        "keychain_delete",
        lambda name: generic_calls.append(name) or {"deleted": name},
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain/delete"
    handler.command = "POST"
    handler.flywheel_home = tmp_path / "home"

    handler._post()

    assert body["code"] == 200
    assert body["obj"] == {"deleted": BULLETIN_CREDENTIAL_NAME}
    assert locked_calls == [handler.flywheel_home / "state"]
    assert generic_calls == []


def test_gateway_keychain_delete_case_alias_uses_identity_store(monkeypatch, tmp_path) -> None:
    from harness import bulletin_identity_store, gateway, keychain
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME

    body: dict = {}
    locked_calls: list[object] = []
    generic_calls: list[str] = []

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        gateway._Handler,
        "_req_json",
        lambda _handler: ({"name": "bulletin_agent_jwk"}, None),
    )
    monkeypatch.setattr(
        bulletin_identity_store,
        "delete_identity_keychain_slot",
        lambda **kwargs: locked_calls.append(kwargs.get("keychain_lock_root"))
        or {"deleted": BULLETIN_CREDENTIAL_NAME},
    )
    monkeypatch.setattr(
        keychain,
        "keychain_delete",
        lambda name: generic_calls.append(name) or {"deleted": name},
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain/delete"
    handler.command = "POST"
    handler.flywheel_home = tmp_path / "home"

    handler._post()

    assert body["code"] == 200
    assert body["obj"] == {"deleted": BULLETIN_CREDENTIAL_NAME}
    assert locked_calls == [handler.flywheel_home / "state"]
    assert generic_calls == []


def test_gateway_keychain_delete_rejects_nul_suffixed_bulletin_slot(monkeypatch, tmp_path) -> None:
    from harness import bulletin_identity_store, gateway, keychain
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME

    body: dict = {}
    identity_calls: list[object] = []
    generic_calls: list[str] = []

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        gateway._Handler,
        "_req_json",
        lambda _handler: ({"name": f"{BULLETIN_CREDENTIAL_NAME}\x00suffix"}, None),
    )
    monkeypatch.setattr(
        bulletin_identity_store,
        "delete_identity_keychain_slot",
        lambda **kwargs: identity_calls.append(kwargs.get("keychain_lock_root"))
        or {"deleted": BULLETIN_CREDENTIAL_NAME},
    )
    monkeypatch.setattr(
        keychain,
        "keychain_delete",
        lambda name: generic_calls.append(name) or {"deleted": name},
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain/delete"
    handler.command = "POST"
    handler.flywheel_home = tmp_path / "home"

    handler._post()

    assert body["code"] == 400
    assert body["obj"]["error"]["code"] == "INVALID_KEYCHAIN_NAME"
    assert identity_calls == []
    assert generic_calls == []
