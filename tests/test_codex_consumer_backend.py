from harness.codex_consumer_backend import CodexConsumerBackend


class FakeClient:
    def __init__(self, account):
        self.account = account
        self.closed = False

    def get_account(self, *, refresh_token=False):
        return self.account

    def read_model_provider_capabilities(self):
        return {"namespaceTools": False, "imageGeneration": False,
                "webSearch": True}

    def list_models(self, *, cursor=None, limit=None, include_hidden=None):
        return {"data": [], "nextCursor": None}

    def close(self):
        self.closed = True


def test_binary_present_alone_is_not_usable():
    backend = CodexConsumerBackend(
        client_factory=lambda: FakeClient({
            "account": None,
            "requiresOpenaiAuth": True,
        }),
        which=lambda _name: "C:/tools/codex.cmd",
        key_source=lambda _env: "absent",
    )

    state = backend.readiness()

    assert state["cli_present"] is True
    assert state["account"]["consumer"]["state"] == "not_authenticated"
    assert state["usable"] is False
    assert state["reason"] == "Codex account not authenticated"


def test_authenticated_consumer_account_is_usable_without_registry_mutation():
    backend = CodexConsumerBackend(
        client_factory=lambda: FakeClient({
            "account": {"type": "chatgpt", "email": None, "planType": "pro"},
            "requiresOpenaiAuth": False,
        }),
        which=lambda _name: "C:/tools/codex.cmd",
        key_source=lambda _env: "absent",
    )

    state = backend.readiness()

    assert state["provider"] == "codex"
    assert state["transport"] == "codex-app-server"
    assert state["usable"] is True
    assert state["account"]["effective_auth_source"] == "consumer-chatgpt"


def test_readiness_closes_one_shot_client_after_probe():
    client = FakeClient({
        "account": None,
        "requiresOpenaiAuth": True,
    })
    backend = CodexConsumerBackend(
        client_factory=lambda: client,
        which=lambda _name: "C:/tools/codex.cmd",
        key_source=lambda _env: "absent",
    )

    state = backend.readiness()

    assert state["usable"] is False
    assert client.closed is True


def test_absent_cli_does_not_attempt_account_probe():
    called = []

    backend = CodexConsumerBackend(
        client_factory=lambda: called.append(True),
        which=lambda _name: None,
        key_source=lambda _env: "absent",
    )

    state = backend.readiness()

    assert state["cli_present"] is False
    assert state["usable"] is False
    assert called == []
