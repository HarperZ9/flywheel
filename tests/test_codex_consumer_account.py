import pytest

from harness.codex_consumer_account import (
    discover_models,
    read_account_state,
    read_capability_snapshot,
    start_managed_login,
)


class FakeClient:
    def __init__(self, *, account=None, models=None, capabilities=None,
                 login=None, failure=None):
        self.account = account or {"account": None, "requiresOpenaiAuth": True}
        self.models = list(models or [])
        self.capabilities = capabilities or {
            "namespaceTools": False,
            "imageGeneration": False,
            "webSearch": False,
        }
        self.login = login or {}
        self.failure = failure
        self.calls = []

    def get_account(self, *, refresh_token=False):
        self.calls.append(("account", refresh_token))
        return self.account

    def start_chatgpt_login(self):
        self.calls.append(("login-browser", None))
        return self.login

    def start_device_code_login(self):
        self.calls.append(("login-device", None))
        return self.login

    def list_models(self, *, cursor=None, limit=None, include_hidden=None):
        self.calls.append(("models", cursor, limit, include_hidden))
        if self.failure:
            raise RuntimeError(self.failure)
        if self.models:
            return self.models.pop(0)
        return {"data": [], "nextCursor": None}

    def read_model_provider_capabilities(self):
        self.calls.append(("capabilities", None))
        return self.capabilities


def test_chatgpt_account_is_consumer_state_without_email_disclosure():
    client = FakeClient(account={
        "account": {"type": "chatgpt", "email": "person@example.test",
                    "planType": "plus"},
        "requiresOpenaiAuth": False,
    })

    state = read_account_state(client, key_source=lambda _env: "absent")

    assert state["consumer"]["state"] == "authenticated"
    assert state["consumer"]["email_present"] is True
    assert "person@example.test" not in repr(state)
    assert state["api_key"]["state"] == "absent"
    assert state["effective_auth_source"] == "consumer-chatgpt"
    assert state["usable_for_codex"] is True


def test_explicit_openai_key_takes_precedence_without_erasing_consumer_state():
    client = FakeClient(account={
        "account": {"type": "chatgpt", "email": None, "planType": "pro"},
        "requiresOpenaiAuth": False,
    })

    state = read_account_state(client, key_source=lambda _env: "env")

    assert state["consumer"]["state"] == "authenticated"
    assert state["api_key"]["state"] == "present"
    assert state["api_key"]["source"] == "env:OPENAI_API_KEY"
    assert state["effective_auth_source"] == "api-key"
    assert state["usable_for_codex"] is True


def test_api_key_account_is_not_reported_as_consumer_chatgpt_auth():
    client = FakeClient(account={
        "account": {"type": "apiKey"},
        "requiresOpenaiAuth": False,
    })

    state = read_account_state(client, key_source=lambda _env: "absent")

    assert state["consumer"]["state"] == "not_consumer_route"
    assert state["api_key"]["state"] == "present"
    assert state["effective_auth_source"] == "api-key"
    assert state["usable_for_codex"] is True


def test_start_managed_login_allows_browser_and_device_only_and_strips_tokens():
    browser = FakeClient(login={
        "type": "chatgpt", "loginId": "B1", "authUrl": "https://auth.test",
        "accessToken": "SECRET",
    })
    device = FakeClient(login={
        "type": "chatgptDeviceCode", "loginId": "D1",
        "verificationUrl": "https://verify.test", "userCode": "ABCD",
        "accessToken": "SECRET",
    })

    assert start_managed_login(browser, mode="browser") == {
        "state": "login_started",
        "mode": "browser",
        "login_id": "B1",
        "auth_url": "https://auth.test",
    }
    assert start_managed_login(device, mode="device_code") == {
        "state": "login_started",
        "mode": "device_code",
        "login_id": "D1",
        "verification_url": "https://verify.test",
        "user_code": "ABCD",
    }
    with pytest.raises(ValueError, match="managed"):
        start_managed_login(browser, mode="chatgptAuthTokens")
    assert "SECRET" not in repr(start_managed_login(device, mode="device_code"))


def test_discover_models_paginates_and_sanitizes_listing_errors():
    client = FakeClient(models=[
        {"data": [{
            "id": "gpt-6-astra",
            "model": "gpt-6-astra",
            "displayName": "GPT-6 Astra",
            "description": "capable",
            "hidden": False,
            "isDefault": True,
            "defaultReasoningEffort": "medium",
            "supportedReasoningEfforts": [
                {"reasoningEffort": "low", "description": "fast"},
            ],
            "inputModalities": ["text", "image"],
            "supportsPersonality": True,
            "serviceTiers": [{"id": "auto", "name": "Auto",
                              "description": "Default"}],
        }], "nextCursor": "n1"},
        {"data": [], "nextCursor": None},
    ])

    out = discover_models(client, include_hidden=False, page_limit=1)

    assert out["reason"] == ""
    assert out["models"][0]["id"] == "gpt-6-astra"
    assert out["models"][0]["supported_reasoning_efforts"] == ["low"]
    assert client.calls[-2:] == [
        ("models", None, 1, False),
        ("models", "n1", 1, False),
    ]

    failed = discover_models(FakeClient(failure="bad sk-SECRET value"))
    assert failed["models"] == []
    assert "SECRET" not in failed["reason"]
    assert "listing unavailable" in failed["reason"]


def test_discover_models_reports_bounded_partial_catalog_when_page_cap_remains():
    pages = [
        {"data": [{
            "id": f"catalog-{i}",
            "model": f"gpt-6-model-{i}",
            "hidden": False,
            "isDefault": False,
            "supportedReasoningEfforts": [],
            "inputModalities": ["text"],
        }], "nextCursor": f"cursor-{i + 1}"}
        for i in range(10)
    ]
    client = FakeClient(models=pages)

    out = discover_models(client, max_pages=10)

    assert len(out["models"]) == 10
    assert out["listing_partial"] is True
    assert out["reason"] == "provider catalog truncated after 10 pages"
    assert client.calls[-1] == ("models", "cursor-9", 100, False)


def test_successful_model_metadata_redacts_secret_shapes_and_validates_reasoning():
    client = FakeClient(models=[{
        "data": [{
            "id": "future.model-2026:alpha",
            "model": "future.model-2026:alpha",
            "displayName": "sk-display-secret",
            "description": "desc sk-secret-value",
            "hidden": False,
            "isDefault": True,
            "defaultReasoningEffort": "medium secret",
            "supportedReasoningEfforts": [
                {"reasoningEffort": "bad effort", "description": "bad"},
                {"reasoningEffort": "ultra", "description": "ok"},
            ],
            "inputModalities": ["text", "audio", "image"],
            "supportsPersonality": False,
            "serviceTiers": [{"id": "sk-tier-secret",
                              "name": "normal tier"}],
        }],
        "nextCursor": None,
    }])

    row = discover_models(client)["models"][0]

    assert row["id"] == "future.model-2026:alpha"
    assert row["model"] == "future.model-2026:alpha"
    assert row["display_name"] == "[redacted]"
    assert row["description"] == "desc [redacted]"
    assert row["default_reasoning_effort"] == "unknown"
    assert row["supported_reasoning_efforts"] == ["ultra"]
    assert row["input_modalities"] == ["text", "image"]
    assert row["service_tiers"] == [{"id": "[redacted]",
                                     "name": "normal tier"}]
    assert "sk-" not in repr(row).lower()


@pytest.mark.parametrize("secret_fields", [
    {"id": "sk-secret-model", "model": "normal.route"},
    {"id": "normal.route", "model": "sk-secret-model"},
    {"id": "sk-secret-model", "model": "sk-secret-model"},
])
def test_secret_shaped_route_identity_is_omitted_not_made_selectable(secret_fields):
    valid_id = "future.model-2026:alpha"
    client = FakeClient(models=[{
        "data": [
            {
                **secret_fields,
                "displayName": "Secret shaped route",
                "description": "display text stays non-route metadata",
                "hidden": False,
                "isDefault": False,
                "defaultReasoningEffort": "low",
                "supportedReasoningEfforts": [
                    {"reasoningEffort": "low", "description": "fast"},
                ],
                "inputModalities": ["text"],
                "supportsPersonality": False,
                "serviceTiers": [],
            },
            {
                "id": valid_id,
                "model": valid_id,
                "displayName": "sk-display-secret",
                "description": "safe visible metadata",
                "hidden": False,
                "isDefault": True,
                "defaultReasoningEffort": "xhigh",
                "supportedReasoningEfforts": [
                    {"reasoningEffort": "xhigh", "description": "deep"},
                ],
                "inputModalities": ["text", "image"],
                "supportsPersonality": True,
                "serviceTiers": [],
            },
        ],
        "nextCursor": None,
    }])

    out = discover_models(client)

    assert out["omitted_model_rows"] == 1
    assert [row["id"] for row in out["models"]] == [valid_id]
    assert out["models"][0]["model"] == valid_id
    assert out["models"][0]["display_name"] == "[redacted]"
    assert "[redacted]" not in [row["id"] for row in out["models"]]
    assert "[redacted]" not in [row["model"] for row in out["models"]]


def test_capability_snapshot_keeps_capability_discovery_separate():
    client = FakeClient(
        account={"account": None, "requiresOpenaiAuth": True},
        capabilities={"namespaceTools": True, "imageGeneration": True,
                      "webSearch": False},
    )

    snapshot = read_capability_snapshot(client, key_source=lambda _env: "absent")

    assert snapshot["account"]["usable_for_codex"] is False
    assert snapshot["capabilities"]["namespace_tools"] is True
    assert snapshot["models"]["models"] == []
