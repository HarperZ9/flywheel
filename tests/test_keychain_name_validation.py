from __future__ import annotations


def test_keychain_entrypoints_reject_control_names_before_native_call(monkeypatch) -> None:
    from harness import keychain

    calls: list[str] = []

    class NativeApi:
        def CredReadW(self, *_args):
            calls.append("read")
            raise AssertionError("invalid credential name reached native read")

        def CredWriteW(self, *_args):
            calls.append("write")
            raise AssertionError("invalid credential name reached native write")

        def CredDeleteW(self, *_args):
            calls.append("delete")
            raise AssertionError("invalid credential name reached native delete")

    monkeypatch.setattr(keychain, "_IS_WINDOWS", True)
    monkeypatch.setattr(keychain, "_advapi32", NativeApi(), raising=False)

    for name in (
            "BULLETIN_AGENT_JWK\x00suffix",
            "OPENAI_API_KEY\nsuffix",
            "OPENAI_API_KEY\x7fsuffix"):
        set_result = keychain.keychain_set(name, "synthetic")
        delete_result = keychain.keychain_delete(name)

        assert set_result["error"]["code"] == "INVALID_KEYCHAIN_NAME"
        assert delete_result["error"]["code"] == "INVALID_KEYCHAIN_NAME"
        assert keychain.keychain_get(name) is None
        assert keychain.resolve_credential(name) == ""
        assert keychain.credential_source(name) == "absent"

    assert calls == []
