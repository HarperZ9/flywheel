from __future__ import annotations


def test_status_is_local_presence_only_and_never_checks_board(monkeypatch) -> None:
    from harness import bulletin_identity_network
    from harness.bulletin_identity_route import bulletin_identity_get

    monkeypatch.setattr(
        bulletin_identity_network,
        "agent_status",
        lambda *_, **__: (_ for _ in ()).throw(AssertionError("network called")),
    )

    body, code = bulletin_identity_get(
        credential_source=lambda _name: "absent",
        keychain_available_fn=lambda: True,
        signing_available_fn=lambda: True,
    )

    assert code == 200
    assert body == {
        "schema": "flywheel.bulletin-identity-status/v1",
        "credential_name": "BULLETIN_AGENT_JWK",
        "source": "absent",
        "keychain_available": True,
        "signing_available": True,
        "create_available": True,
        "register_available": False,
        "unavailable_reason": None,
    }
    assert "thumbprint" not in body
    assert "key" not in body
    assert "public_jwk" not in body


def test_status_reports_keychain_identity_as_registerable() -> None:
    from harness.bulletin_identity_route import bulletin_identity_get

    body, code = bulletin_identity_get(
        credential_source=lambda _name: "keychain",
        keychain_available_fn=lambda: True,
        signing_available_fn=lambda: True,
    )

    assert code == 200
    assert body["source"] == "keychain"
    assert body["create_available"] is False
    assert body["register_available"] is True


def test_status_fails_closed_when_required_signing_import_fails(monkeypatch) -> None:
    from harness import bulletin_identity_route

    def import_module(name: str):
        if name == "cryptography.hazmat.primitives.asymmetric.ed25519":
            raise OSError("native backend missing")
        return object()

    monkeypatch.setattr(bulletin_identity_route, "find_spec", lambda _name: object())
    monkeypatch.setattr(bulletin_identity_route, "import_module", import_module, raising=False)

    body, code = bulletin_identity_route.bulletin_identity_get(
        credential_source=lambda _name: "absent",
        keychain_available_fn=lambda: True,
    )

    assert code == 200
    assert body["signing_available"] is False
    assert body["create_available"] is False
    assert body["register_available"] is False
    assert body["unavailable_reason"] == "SIGNING_UNAVAILABLE"


def test_create_requires_explicit_confirmation(tmp_path) -> None:
    from harness.bulletin_identity_route import bulletin_identity_create_post

    body, code = bulletin_identity_create_post(
        {"schema": "flywheel.bulletin-identity-create-request/v1", "action": "create"},
        tmp_path,
        create_identity=lambda **_: (_ for _ in ()).throw(AssertionError("created")),
    )

    assert code == 400
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_create_stores_local_identity_only_without_registration(tmp_path) -> None:
    from types import SimpleNamespace
    from harness.bulletin_identity_route import bulletin_identity_create_post

    calls: list[object] = []

    def create_identity(**kwargs):
        calls.append(kwargs["keychain_lock_root"])
        return SimpleNamespace(raw_json="private", thumbprint="tp"), {
            "credential_name": "BULLETIN_AGENT_JWK",
            "source": "keychain",
            "action": "created_stored",
            "thumbprint": "tp",
        }

    body, code = bulletin_identity_create_post(
        {
            "schema": "flywheel.bulletin-identity-create-request/v1",
            "action": "create",
            "confirm_create": True,
        },
        tmp_path,
        credential_source=lambda _name: "absent",
        keychain_available_fn=lambda: True,
        signing_available_fn=lambda: True,
        create_identity=create_identity,
    )

    assert code == 200
    assert body["action"] == "created_stored"
    assert body["source"] == "keychain"
    assert calls == [tmp_path / "state"]
    assert "thumbprint" not in body
    assert "raw_json" not in body
    assert "key" not in body


def test_create_rejects_client_supplied_registration_controls(tmp_path) -> None:
    from harness.bulletin_identity_route import bulletin_identity_create_post

    body, code = bulletin_identity_create_post(
        {
            "schema": "flywheel.bulletin-identity-create-request/v1",
            "action": "create",
            "confirm_create": True,
            "base_url": "http://127.0.0.1:9",
        },
        tmp_path,
        create_identity=lambda **_: (_ for _ in ()).throw(AssertionError("created")),
    )

    assert code == 400
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_register_requires_explicit_confirmation(tmp_path) -> None:
    from harness.bulletin_identity_route import bulletin_identity_register_post

    body, code = bulletin_identity_register_post(
        {"schema": "flywheel.bulletin-identity-register-request/v1", "action": "register"},
        tmp_path,
        prepare=lambda **_: (_ for _ in ()).throw(AssertionError("registered")),
    )

    assert code == 400
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_register_refuses_missing_capabilities_before_prepare(tmp_path) -> None:
    from harness.bulletin_identity_route import bulletin_identity_register_post

    req = {"schema": "flywheel.bulletin-identity-register-request/v1", "action": "register", "confirm_register": True}
    for keychain, signing, want in ((False, True, "KEYCHAIN_UNAVAILABLE"), (True, False, "SIGNING_UNAVAILABLE")):
        body, code = bulletin_identity_register_post(
            req, tmp_path, prepare=lambda **_: (_ for _ in ()).throw(AssertionError("prepared")),
            keychain_available_fn=lambda keychain=keychain: keychain,
            signing_available_fn=lambda signing=signing: signing)
        assert code == 400
        assert body["error"]["code"] == want


def test_register_uses_fixed_production_origin_and_sanitizes_result(tmp_path) -> None:
    from harness.bulletin_identity_contract import DEFAULT_BASE_URL, DEFAULT_HANDLE, MAX_POW_BITS
    from harness.bulletin_identity_route import bulletin_identity_register_post

    captured: dict = {}

    def prepare(**kwargs):
        captured.update(kwargs)
        return {
            "schema": "flywheel.bulletin-identity-prepare/v1",
            "credential_name": "BULLETIN_AGENT_JWK",
            "thumbprint": "secret-ish-public-id",
            "key": {"public_key": "verified"},
            "base_url": DEFAULT_BASE_URL,
            "board": {"registered": True, "handle": DEFAULT_HANDLE, "tier": "agent"},
            "registration": {
                "requested": True,
                "action": "registered",
                "registered": True,
                "handle": DEFAULT_HANDLE,
                "tier": "agent",
            },
            "keychain": {"source": "keychain", "action": "reused", "thumbprint": "tp"},
        }

    body, code = bulletin_identity_register_post(
        {
            "schema": "flywheel.bulletin-identity-register-request/v1",
            "action": "register",
            "confirm_register": True,
        },
        tmp_path,
        prepare=prepare,
        keychain_available_fn=lambda: True,
        signing_available_fn=lambda: True,
    )

    assert code == 200
    assert captured["base_url"] == DEFAULT_BASE_URL
    assert captured["handle"] == DEFAULT_HANDLE
    assert captured["allow_loopback"] is False
    assert captured["max_pow_bits"] == MAX_POW_BITS
    assert captured["register"] is True
    assert captured["store_keychain"] is False
    assert captured["bind_owner"] is None
    assert captured["state_root"] == tmp_path / "state"
    assert captured["keychain_lock_root"] == tmp_path / "state"
    assert body["action"] == "registered"
    assert body["registration"]["registered"] is True
    assert "thumbprint" not in body
    assert "key" not in body
    assert "public_jwk" not in body


def test_register_rejects_client_origin_or_pow_override(tmp_path) -> None:
    from harness.bulletin_identity_route import bulletin_identity_register_post

    body, code = bulletin_identity_register_post(
        {
            "schema": "flywheel.bulletin-identity-register-request/v1",
            "action": "register",
            "confirm_register": True,
            "allow_loopback": True,
        },
        tmp_path,
        prepare=lambda **_: (_ for _ in ()).throw(AssertionError("registered")),
    )

    assert code == 400
    assert body["error"]["code"] == "INVALID_REQUEST"


def test_gateway_dispatches_identity_status(monkeypatch) -> None:
    from harness import bulletin_identity_route, gateway

    body: dict = {}

    def capture_json(_handler, obj, code=200):
        body["obj"] = obj
        body["code"] = code
        return obj

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(
        bulletin_identity_route,
        "bulletin_identity_get",
        lambda: ({"schema": "flywheel.bulletin-identity-status/v1"}, 200),
    )
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/bulletin-identity"
    handler.command = "GET"

    handler._get()

    assert body == {
        "obj": {"schema": "flywheel.bulletin-identity-status/v1"},
        "code": 200,
    }


def test_gateway_dispatches_identity_create_and_register(monkeypatch, tmp_path) -> None:
    from harness import bulletin_identity_route, gateway

    calls: list[tuple[str, dict, object]] = []

    def capture_json(_handler, obj, code=200):
        return {"obj": obj, "code": code}

    def create(req, home):
        calls.append(("create", req, home))
        return {"action": "created_stored"}, 200

    def register(req, home):
        calls.append(("register", req, home))
        return {"action": "registered"}, 200

    monkeypatch.setattr(gateway._Handler, "_json", capture_json)
    monkeypatch.setattr(bulletin_identity_route, "bulletin_identity_create_post", create)
    monkeypatch.setattr(bulletin_identity_route, "bulletin_identity_register_post", register)

    for path in ("/api/bulletin-identity/create", "/api/bulletin-identity/register"):
        handler = gateway._Handler.__new__(gateway._Handler)
        handler.path = path
        handler.command = "POST"
        handler.flywheel_home = tmp_path / "home"
        handler._req_json = lambda: ({"schema": "request"}, None)

        handler._post()

    assert calls == [
        ("create", {"schema": "request"}, tmp_path / "home"),
        ("register", {"schema": "request"}, tmp_path / "home"),
    ]
