class FakeClient:
    def __init__(
            self, *, account=None, login=None, notifications=None,
            cancel_status="canceled", capabilities=None, fail_pop=False,
            notification_overflow=False):
        self.account = account or {"account": None, "requiresOpenaiAuth": True}
        self.login = login or {}
        self.notifications = list(notifications or [])
        self.cancel_status = cancel_status
        self.capabilities = capabilities or {
            "namespaceTools": False,
            "imageGeneration": False,
            "webSearch": False,
        }
        self.fail_pop = fail_pop
        self.notification_overflow = notification_overflow
        self.calls = []
        self.closed = False

    def get_account(self, *, refresh_token=False):
        self.calls.append(("account", refresh_token))
        return self.account

    def read_model_provider_capabilities(self):
        self.calls.append(("capabilities", None))
        return self.capabilities

    def start_chatgpt_login(self):
        self.calls.append(("login-browser", None))
        return self.login

    def start_device_code_login(self):
        self.calls.append(("login-device", None))
        return self.login

    def cancel_login(self, login_id):
        self.calls.append(("cancel", login_id))
        return {"status": self.cancel_status}

    def logout(self):
        self.calls.append(("logout", None))
        return {}

    def pop_notification(self, timeout=0.0):
        self.calls.append(("notification", timeout))
        if self.fail_pop:
            raise RuntimeError("bad sk-SECRET")
        if self.notifications:
            return self.notifications.pop(0)
        return None

    def notification_overflowed(self):
        return self.notification_overflow

    def close(self):
        self.closed = True


class ClientFactory:
    def __init__(self, *clients):
        self.pending = list(clients)
        self.created = []

    def __call__(self):
        if not self.pending:
            raise AssertionError("unexpected client creation")
        client = self.pending.pop(0)
        self.created.append(client)
        return client


def browser_login(login_id="login-1", url=None):
    return {
        "type": "chatgpt",
        "loginId": login_id,
        "authUrl": url or f"https://auth.openai.com/login/{login_id}",
    }


def manager_with(manager_cls, *clients, clock=None, ttl_seconds=600):
    return manager_cls(
        client_factory=ClientFactory(*clients),
        key_source=lambda _env: "absent",
        clock=clock,
        ttl_seconds=ttl_seconds,
    )
