import harness.model_roster as MR


class FakeCodexModelsClient:
    def __init__(self, pages=(), failure=None):
        self.pages = list(pages)
        self.failure = failure
        self.calls = []
        self.closed = False

    def list_models(self, *, cursor=None, limit=None, include_hidden=None):
        self.calls.append({
            "cursor": cursor,
            "limit": limit,
            "include_hidden": include_hidden,
        })
        if self.failure is not None:
            raise RuntimeError(self.failure)
        return self.pages.pop(0) if self.pages else {"data": []}

    def close(self):
        self.closed = True


def _row(catalog_id, route, *, default=False, hidden=False):
    return {
        "id": catalog_id,
        "model": route,
        "displayName": f"Display {catalog_id}",
        "hidden": hidden,
        "isDefault": default,
        "defaultReasoningEffort": "high",
        "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
        "inputModalities": ["text"],
    }


def _roster(*, client, configured_default="codex"):
    from harness.codex_consumer_models import codex_consumer_roster

    return codex_consumer_roster(
        "codex-cli",
        configured_default,
        timeout=1.25,
        client_factory=lambda **_kwargs: client,
    )


def test_codex_cli_roster_uses_route_as_picker_id_and_keeps_catalog_id():
    client = FakeCodexModelsClient([
        {"data": [_row("catalog-astra", "gpt-6-astra", default=True)]}
    ])

    out = _roster(client=client)

    assert client.closed is True
    assert client.calls == [{"cursor": None, "limit": 100, "include_hidden": False}]
    assert out["endpoint"] == "codex-cli"
    assert out["configured_default_model"] == "codex"
    assert out["endpoint_default_selectable"] is False
    assert out["default_model_source"] == "provider_catalog"
    assert out["provider_listed_models"] == ["catalog-astra"]
    assert out["provider_listed_model_routes"] == ["gpt-6-astra"]
    assert out["actual_provider_default"] == {
        "catalog_id": "catalog-astra",
        "model": "gpt-6-astra",
    }
    assert out["models"][0]["id"] == "gpt-6-astra"
    assert out["models"][0]["model"] == "gpt-6-astra"
    assert out["models"][0]["catalog_id"] == "catalog-astra"
    assert out["models"][0]["default"] == "true"


def test_codex_cli_roster_omits_hidden_and_duplicate_rows_then_fails_ambiguous_default_closed():
    client = FakeCodexModelsClient([
        {"data": [
            _row("catalog-astra", "gpt-6-astra", default=True),
            _row("catalog-hidden", "gpt-6-hidden", default=True, hidden=True),
            _row("catalog-duplicate", "gpt-6-astra"),
            _row("catalog-sol", "gpt-6-sol", default=True),
        ]}
    ])

    out = _roster(client=client)

    assert [row["id"] for row in out["models"]] == ["gpt-6-astra", "gpt-6-sol"]
    assert [row["catalog_id"] for row in out["models"]] == [
        "catalog-astra",
        "catalog-sol",
    ]
    assert all(row["default"] == "false" for row in out["models"])
    assert out["actual_provider_default"] is None
    assert out["default_model_source"] == "none"
    assert out["default_provider_listed"] is False
    assert out["endpoint_default_selectable"] is False
    assert out["omitted_model_rows"] == 2
    assert "ambiguous default" in out["reason"]


def test_codex_cli_roster_catalog_failure_has_no_fake_fallback_and_closes_client():
    client = FakeCodexModelsClient(failure="sk-secret should not leak")

    out = _roster(client=client)

    assert client.closed is True
    assert out["models"] == []
    assert out["provider_listed_models"] == []
    assert out["provider_listed_model_routes"] == []
    assert out["actual_provider_default"] is None
    assert out["endpoint_default_selectable"] is False
    assert "RuntimeError" in out["reason"]
    assert "sk-secret" not in out["reason"]
    assert "codex" not in [row["id"] for row in out["models"]]


def test_codex_cli_roster_factory_failure_has_no_fake_fallback_or_secret():
    from harness.codex_consumer_models import codex_consumer_roster

    def fail_factory(**_kwargs):
        raise RuntimeError("sk-secret launch detail")

    out = codex_consumer_roster(
        "codex-cli",
        "codex",
        timeout=1.25,
        client_factory=fail_factory,
    )

    assert out["models"] == []
    assert out["endpoint_default_selectable"] is False
    assert out["actual_provider_default"] is None
    assert "RuntimeError" in out["reason"]
    assert "sk-secret" not in out["reason"]


def test_codex_cli_roster_preserves_partial_catalog_reason_before_default_warning():
    client = FakeCodexModelsClient([
        {"data": [_row(f"catalog-{i}", f"gpt-6-model-{i}")],
         "nextCursor": f"cursor-{i + 1}"}
        for i in range(10)
    ])

    out = _roster(client=client)

    assert len(client.calls) == 10
    assert client.closed is True
    assert out["listing_partial"] is True
    assert out["reason"].startswith(
        "provider catalog truncated after 10 pages")
    assert "provider catalog did not report a default model" in out["reason"]


def test_model_roster_codex_cli_uses_consumer_catalog(monkeypatch):
    calls = []

    def fake_codex_catalog(endpoint, configured_default, *, timeout):
        calls.append((endpoint, configured_default, timeout))
        return {
            "endpoint": endpoint,
            "models": [{"id": "gpt-6-astra", "default": "true"}],
            "reason": "",
            "endpoint_default_selectable": False,
        }

    monkeypatch.setattr(MR, "_codex_consumer_roster", fake_codex_catalog)

    out = MR.list_models("codex-cli", timeout=1.25)

    assert calls == [("codex-cli", "codex", 1.25)]
    assert out["models"] == [{"id": "gpt-6-astra", "default": "true"}]
    assert out["endpoint_default_selectable"] is False
