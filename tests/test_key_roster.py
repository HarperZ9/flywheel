from __future__ import annotations


def test_declared_key_names_include_bulletin_without_provider() -> None:
    from harness.endpoints import PROVIDERS
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME, declared_key_names

    names = declared_key_names({"openai": {"key": "OPENAI_API_KEY"}})

    assert "OPENAI_API_KEY" in names
    assert BULLETIN_CREDENTIAL_NAME == "BULLETIN_AGENT_JWK"
    assert BULLETIN_CREDENTIAL_NAME in names
    assert all(spec.get("key") != BULLETIN_CREDENTIAL_NAME for spec in PROVIDERS.values())


def test_keychain_entries_are_presence_only() -> None:
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME, keychain_entries

    seen: list[str] = []

    def source(name: str) -> str:
        seen.append(name)
        return "keychain" if name == BULLETIN_CREDENTIAL_NAME else "absent"

    entries = keychain_entries(
        credential_source=source,
        providers={"openai": {"key": "OPENAI_API_KEY"}},
    )

    bulletin = next(item for item in entries if item["name"] == BULLETIN_CREDENTIAL_NAME)
    assert bulletin == {
        "name": BULLETIN_CREDENTIAL_NAME,
        "source": "keychain",
        "kind": "native_identity",
        "protected": True,
        "generic_set_allowed": False,
        "set_action": "bulletin_identity",
        "purpose": "Bulletin Ed25519 signing identity JWK",
    }
    assert "value" not in bulletin
    assert "secret" not in bulletin
    assert set(seen) == {"OPENAI_API_KEY", BULLETIN_CREDENTIAL_NAME}


def test_gateway_keychain_route_includes_bulletin_presence(monkeypatch) -> None:
    from harness import gateway, keychain
    from harness.key_roster import BULLETIN_CREDENTIAL_NAME

    body: dict = {}

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(
        keychain,
        "credential_source",
        lambda name: "keychain" if name == BULLETIN_CREDENTIAL_NAME else "absent",
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/keychain"
    handler.command = "GET"

    handler._get()

    assert body["code"] == 200
    entry = next(
        item for item in body["obj"]["entries"]
        if item["name"] == BULLETIN_CREDENTIAL_NAME
    )
    assert entry["name"] == BULLETIN_CREDENTIAL_NAME
    assert entry["source"] == "keychain"
    assert entry["generic_set_allowed"] is False
    assert entry["set_action"] == "bulletin_identity"
