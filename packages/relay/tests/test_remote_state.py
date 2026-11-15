"""test_remote_state.py -- the readout of the phone-facing surface.

Two things are under test. First, that the readout tells the truth about a
surface running in another process: off when it is off, on when it is on, and
half-configured when the OAuth block is incomplete, which is the case the server
itself passes over in silence. Second, that it never hands back a secret. The
control for that is a sentinel sweep: every key is set to a value found nowhere
else, and no presence-only sentinel may appear anywhere in the serialized state.
"""
from __future__ import annotations

import json

import pytest

from relay.remote_mcp import config_from_env
from relay.remote_state import (
    OAUTH_REQUIRED,
    PRESENCE_ONLY,
    VALUE_SAFE,
    env_file_path,
    remote_state,
    resolved_env,
)

FULL_OAUTH = {
    "RELAY_OAUTH_CLIENT_ID": "cid", "RELAY_OAUTH_CLIENT_SECRET": "csec",
    "RELAY_OAUTH_SIGNING_SECRET": "sign", "RELAY_PUBLIC_URL": "https://board.example",
    "RELAY_AUTHORIZE_PASSWORD": "pw", "RELAY_OAUTH_REDIRECT_URIS": "https://a/cb",
}


def _state(env, missing_file="nonexistent.env"):
    """Read state from an explicit environment and no env file on disk."""
    return remote_state(env, env_file=missing_file)


def test_no_token_means_the_surface_is_off_and_says_why():
    state = _state({})
    assert state["configured"] is False
    # An off surface with no reason reads as a failure to check.
    assert "RELAY_REMOTE_TOKEN" in state["reason"]


def test_a_token_alone_configures_the_surface():
    state = _state({"RELAY_REMOTE_TOKEN": "t"})
    assert state["configured"] is True
    assert state["reason"] == ""
    # The bearer path, with no phone connector and no TLS.
    assert state["oauth_configured"] is False
    assert state["tls_configured"] is False


def test_no_secret_value_reaches_the_output():
    """The control. Every key gets a sentinel; no presence-only one may escape."""
    keys = set(PRESENCE_ONLY) | set(VALUE_SAFE)
    env = {key: f"sentinel-value-for-{key}" for key in keys}
    blob = json.dumps(_state(env))
    for key in PRESENCE_ONLY:
        assert f"sentinel-value-for-{key}" not in blob, f"{key} leaked its value"
    # Not a vacuous pass: the value-safe keys do come back, so the sweep is
    # reading a state that carries values at all.
    assert "sentinel-value-for-RELAY_PUBLIC_URL" in blob


def test_every_key_the_surface_reads_is_classified_exactly_once():
    # A key in neither set is one nobody decided about, and a key in both is a
    # contradiction that the sentinel sweep above would not catch.
    assert not (set(PRESENCE_ONLY) & set(VALUE_SAFE))
    for key in OAUTH_REQUIRED:
        assert key in set(PRESENCE_ONLY) | set(VALUE_SAFE), key


def test_a_half_configured_oauth_reads_as_off_and_names_what_is_missing():
    """The trap this readout exists for.

    `_oauth_from_env` returns None unless all six keys are set, and the server
    then serves the static bearer with no phone connector and no complaint. Five
    of six looks configured to anyone reading the .env by eye.
    """
    env = {"RELAY_REMOTE_TOKEN": "t", **FULL_OAUTH}
    del env["RELAY_AUTHORIZE_PASSWORD"]
    state = _state(env)
    assert state["oauth_configured"] is False
    assert state["oauth_missing"] == ["RELAY_AUTHORIZE_PASSWORD"]
    # The surface still serves; only the phone connector is absent.
    assert state["configured"] is True


def test_all_six_oauth_keys_turn_the_phone_connector_on():
    state = _state({"RELAY_REMOTE_TOKEN": "t", **FULL_OAUTH})
    assert state["oauth_configured"] is True
    assert state["oauth_missing"] == []
    assert state["public_url"] == "https://board.example"


@pytest.mark.parametrize("dropped", sorted(OAUTH_REQUIRED))
def test_any_one_missing_oauth_key_turns_the_connector_off(dropped):
    env = {"RELAY_REMOTE_TOKEN": "t", **FULL_OAUTH}
    del env[dropped]
    state = _state(env)
    assert state["oauth_configured"] is False
    assert dropped in state["oauth_missing"]


def test_the_readout_agrees_with_the_server_s_own_config_function():
    """The check on the check.

    `configured` could be an independent reimplementation that drifts from the
    function the server actually gates on. It is compared against it here for
    every case that matters.
    """
    cases = [{}, {"RELAY_REMOTE_TOKEN": "t"}, {"RELAY_REMOTE_TOKEN": ""},
             {**FULL_OAUTH}, {"RELAY_REMOTE_TOKEN": "t", **FULL_OAUTH}]
    for env in cases:
        assert _state(env)["configured"] is (config_from_env(env) is not None), env


def test_the_env_file_is_read_and_the_real_environment_wins(tmp_path):
    # The composition remote_cli serves from: file first, environment over it.
    env_file = tmp_path / "relay.env"
    env_file.write_text("RELAY_REMOTE_TOKEN=from-file\n"
                        "# a comment\n"
                        "RELAY_PUBLIC_URL='https://from-file.example'\n", encoding="utf-8")
    resolved, path = resolved_env({"RELAY_PUBLIC_URL": "https://from-env.example"},
                                  env_file=str(env_file))
    assert path == str(env_file)
    assert resolved["RELAY_REMOTE_TOKEN"] == "from-file"
    assert resolved["RELAY_PUBLIC_URL"] == "https://from-env.example"
    state = remote_state({"RELAY_PUBLIC_URL": "https://from-env.example"},
                         env_file=str(env_file))
    assert state["configured"] is True and state["env_file_found"] is True


def test_a_missing_env_file_is_reported_rather_than_guessed():
    # "Off" and "I read the wrong file" are different facts, and a client that
    # cannot tell them apart will tell an operator their working setup is off.
    state = _state({}, missing_file="no-such-file.env")
    assert state["env_file"] == "no-such-file.env"
    assert state["env_file_found"] is False


def test_the_env_file_name_follows_the_variable_the_entrypoint_reads():
    assert env_file_path({}) == ".env"
    assert env_file_path({"RELAY_ENV_FILE": "other.env"}) == "other.env"


@pytest.mark.parametrize("raw,allowed", [("1", True), ("true", True), ("TRUE", True),
                                         ("yes", True), ("on", True), ("", False),
                                         ("0", False), ("no", False), ("off", False)])
def test_remote_exec_is_off_unless_it_is_explicitly_allowed(raw, allowed):
    # Parsed like RELAY_ALLOW_WRITE / RELAY_ALLOW_EXEC; "maybe" is an error,
    # covered in test_remote_launch_env.py.
    state = _state({"RELAY_REMOTE_TOKEN": "t", "RELAY_ALLOW_REMOTE_EXEC": raw})
    assert state["remote_exec_allowed"] is allowed


def test_tls_needs_both_halves():
    half = _state({"RELAY_REMOTE_TOKEN": "t", "RELAY_TLS_CERT": "cert.pem"})
    assert half["tls_configured"] is False
    both = _state({"RELAY_REMOTE_TOKEN": "t", "RELAY_TLS_CERT": "c", "RELAY_TLS_KEY": "k"})
    assert both["tls_configured"] is True


def test_origins_are_split_deduped_and_sorted():
    state = _state({"RELAY_REMOTE_TOKEN": "t",
                    "RELAY_ALLOWED_ORIGINS": "https://b.example, https://a.example ,https://b.example,"})
    assert state["allowed_origins"] == ["https://a.example", "https://b.example"]


def test_no_origins_is_an_empty_list_not_a_missing_key():
    # An absent list and an empty one render the same way downstream; a client
    # reading `.get("allowed_origins")` should never get None here.
    assert _state({"RELAY_REMOTE_TOKEN": "t"})["allowed_origins"] == []


def test_the_listen_address_comes_back_whole_or_null():
    state = _state({"RELAY_REMOTE_TOKEN": "t", "RELAY_REMOTE_HOST": "0.0.0.0",
                    "RELAY_REMOTE_PORT": "8787"})
    assert state["listen"] == {"host": "0.0.0.0", "port": "8787"}
    assert _state({})["listen"] == {"host": None, "port": None}


def test_keys_present_is_booleans_only():
    env = {key: "x" for key in PRESENCE_ONLY}
    present = _state(env)["keys_present"]
    assert set(present) == set(PRESENCE_ONLY)
    assert all(v is True for v in present.values())
    assert all(v is False for v in _state({})["keys_present"].values())


def test_the_launch_grants_are_read_out_and_a_bad_value_is_named():
    # remote_cli configures write/exec from these keys, so the readout reports
    # what the surface would grant, and a typo reads as an error, not as off.
    state = _state({"RELAY_REMOTE_TOKEN": "t", "RELAY_ALLOW_WRITE": "1"})
    assert state["start_grants"] == {"allow_write": True, "allow_exec": False,
                                     "root": None, "agent_cli_tiers": False,
                                     "shell_path_confined": False}
    assert _state({"RELAY_MCP_ROOT": "/w"})["start_grants"]["root"] == "/w"
    assert _state({})["start_grants"]["allow_exec"] is False
    bad = _state({"RELAY_ALLOW_EXEC": "maybe"})["start_grants"]
    assert "RELAY_ALLOW_EXEC" in bad["error"]
