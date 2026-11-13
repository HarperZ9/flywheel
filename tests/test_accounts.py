"""Falsifiers for named accounts: several keys per provider, one active, and
no key in any listing, message or index file. The credential store is a dict
here; the OS store is never touched."""
import json

import pytest

from harness import accounts, auth_cli, keychain, setup_cli

KEY_A = "sk-" + "ant-" + "a" * 40
KEY_B = "sk-" + "ant-" + "b" * 40
ENV = "ANTHROPIC_API_KEY"


class FakeStore:
    def __init__(self, items=None):
        self.items = dict(items or {})

    def available(self):
        return True

    def get(self, name):
        return self.items.get(name)

    def set(self, name, secret):
        self.items[name] = secret
        return {"stored": name}

    def delete(self, name):
        if name not in self.items:
            return {"error": f"no stored credential named '{name}'"}
        del self.items[name]
        return {"deleted": name}


@pytest.fixture
def index(tmp_path):
    return tmp_path / "accounts.json"


def test_a_key_stored_before_named_accounts_is_the_default_account(index):
    store = FakeStore({ENV: KEY_A})
    row = next(r for r in accounts.list_accounts(store, index, {})
               if r["provider"] == "anthropic")
    assert row["labels"] == ["default"] and row["active"] == "default"
    assert not index.exists(), "listing must not write or migrate anything"


def test_second_account_is_parked_and_the_slot_keeps_the_active_key(index):
    store = FakeStore({ENV: KEY_A})
    done = accounts.add_account("anthropic", "work", KEY_B, store, index)
    assert done["active"] is False
    assert store.items == {ENV: KEY_A, f"{ENV}@work": KEY_B}


def test_first_account_for_a_provider_becomes_active(index):
    store = FakeStore()
    assert accounts.add_account("openai", "work", KEY_A, store, index)["active"] is True
    assert store.items == {"OPENAI_API_KEY": KEY_A}


def test_use_switches_the_slot_and_parks_the_previous_key(index):
    store = FakeStore({ENV: KEY_A})
    accounts.add_account("anthropic", "work", KEY_B, store, index)
    assert accounts.use_account("anthropic", "work", store, index)["changed"] is True
    assert store.items == {ENV: KEY_B, f"{ENV}@default": KEY_A}
    accounts.use_account("anthropic", "default", store, index)
    assert store.items == {ENV: KEY_A, f"{ENV}@work": KEY_B}
    row = accounts.list_accounts(store, index, {})[0]
    assert row["active"] == "default" and row["labels"] == ["default", "work"]


def test_use_refuses_an_unknown_account_and_changes_nothing(index):
    store = FakeStore({ENV: KEY_A})
    with pytest.raises(accounts.AccountsError) as err:
        accounts.use_account("anthropic", "nope", store, index)
    assert "flywheel setup --provider anthropic --account nope" in str(err.value)
    assert store.items == {ENV: KEY_A}


def test_remove_deletes_the_key_and_reports_no_active_account(index):
    store = FakeStore({ENV: KEY_A})
    accounts.add_account("anthropic", "work", KEY_B, store, index)
    done = accounts.remove_account("anthropic", "default", store, index)
    assert done["was_active"] and done["remaining"] == ["work"] and done["key_found"]
    assert store.items == {f"{ENV}@work": KEY_B}
    row = accounts.list_accounts(store, index, {})[0]
    assert row["active"] is None and row["labels"] == ["work"]
    accounts.remove_account("anthropic", "work", store, index)
    assert store.items == {}


def test_a_store_that_refuses_the_write_is_reported_and_nothing_is_listed(index):
    class Refusing(FakeStore):
        def set(self, name, secret):
            return {"error": {"code": "X", "message": "store is locked"}}
    with pytest.raises(accounts.AccountsError) as err:
        accounts.add_account("gemini", "work", KEY_A, Refusing(), index)
    assert "store is locked" in str(err.value) and KEY_A not in str(err.value)
    assert not index.exists()


@pytest.mark.parametrize("label", ["", "has space", "a/b", "x" * 33, "-lead", "a@b"])
def test_unsafe_labels_are_refused(label, index):
    with pytest.raises(accounts.AccountsError):
        accounts.add_account("openai", label, KEY_A, FakeStore(), index)


def test_unknown_provider_is_named(index):
    with pytest.raises(accounts.AccountsError) as err:
        accounts.use_account("nope", "work", FakeStore(), index)
    assert "unknown provider 'nope'" in str(err.value)


def test_a_damaged_index_is_reported_with_its_path(index):
    index.write_text("{not json", encoding="utf-8")
    with pytest.raises(accounts.AccountsError) as err:
        accounts.list_accounts(FakeStore(), index, {})
    assert str(index) in str(err.value)


def test_no_key_reaches_the_index_file_or_any_output(index, monkeypatch, capsys, tmp_path):
    store = FakeStore({ENV: KEY_A})
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    monkeypatch.setattr(accounts, "KeychainStore", lambda: store)
    monkeypatch.setattr(keychain, "keychain_available", lambda: True)
    ok, message = setup_cli.store("anthropic", read_secret=lambda p: KEY_B, account="work")
    assert ok and "flywheel auth use anthropic work" in message
    assert auth_cli.main(["list"]) == 0
    assert auth_cli.main(["use", "anthropic", "work"]) == 0
    assert auth_cli.main(["use", "anthropic", "work"]) == 0
    assert auth_cli.main(["remove", "anthropic", "default"]) == 0
    assert auth_cli.main(["remove", "anthropic", "missing"]) == 1
    captured = capsys.readouterr()
    shown = captured.out + captured.err + message + (tmp_path / "accounts.json").read_text("utf-8")
    for key in (KEY_A, KEY_B):
        assert key not in shown and key[:10] not in shown and key[-6:] not in shown
    assert "*default, work" in captured.out and "now uses the account 'work'" in captured.out
    assert json.loads((tmp_path / "accounts.json").read_text("utf-8"))["providers"][
        "anthropic"] == {"active": "work", "labels": ["work"]}


def test_list_names_an_environment_variable_that_wins():
    rows = [{"provider": "openai", "env": "OPENAI_API_KEY", "labels": ["default", "work"],
             "active": "work", "env_override": True},
            {"provider": "gemini", "env": "GEMINI_API_KEY", "labels": [],
             "active": None, "env_override": False}]
    text = auth_cli.render_list(rows)
    assert "default, *work" in text and "OPENAI_API_KEY is set in the environment" in text
    assert "gemini      no stored account" in text


def test_auth_help_prints_help_and_reads_no_account(monkeypatch, capsys):
    monkeypatch.setattr(accounts, "list_accounts",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("read")))
    from harness import oauth_signin
    monkeypatch.setattr(oauth_signin, "status",
                        lambda: (_ for _ in ()).throw(AssertionError("status ran")))
    for argv in (["--help"], ["-h"], ["login", "--help"]):
        assert auth_cli.main(argv) == 0
    out = capsys.readouterr().out
    assert "flywheel auth list" in out and "flywheel auth use PROVIDER LABEL" in out


def test_unknown_auth_verb_is_an_error_with_usage(capsys):
    assert auth_cli.main(["swtich", "openai", "work"]) == 2
    assert "`flywheel auth swtich` is not a command" in capsys.readouterr().err


def test_use_and_remove_need_both_names(capsys):
    assert auth_cli.main(["use", "openai"]) == 2
    assert "usage: flywheel auth use PROVIDER LABEL" in capsys.readouterr().err
