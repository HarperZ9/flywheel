"""House-voice settings: on by default, off with one switch, tunable through a
closed set of keys, and written only by the command line."""
import json

import pytest

from articulate import cli, house_settings


def test_the_house_voice_is_off_by_default(tmp_path):
    s = house_settings.resolve(environ={"ARTICULATE_CONFIG_DIR": str(tmp_path)})
    assert house_settings.DEFAULT_MODE == "off"
    assert s["mode"] == "off"
    assert s["sources"]["mode"] == "default"
    assert set(s["tuning"]) == set(house_settings.TUNING)


def test_an_explicit_request_opts_in_unless_the_user_chose_a_mode(tmp_path):
    env = {"ARTICULATE_CONFIG_DIR": str(tmp_path)}
    s = house_settings.for_request(environ=env)
    assert (s["mode"], s["sources"]["mode"]) == ("default", "request")
    off = house_settings.for_request(environ=dict(env, ARTICULATE_HOUSE_VOICE="off"))
    assert (off["mode"], off["sources"]["mode"]) == ("off", "env")
    brief_only = house_settings.for_request(environ=env, overrides={"mode": "brief"})
    assert brief_only["mode"] == "brief"


def test_on_turns_it_on(tmp_path):
    env = {"ARTICULATE_CONFIG_DIR": str(tmp_path), "ARTICULATE_HOUSE_VOICE": "on"}
    assert house_settings.resolve(environ=env)["mode"] == "default"


@pytest.mark.parametrize("value", ["off", "OFF", "0", "false", "no"])
def test_env_turns_it_off(tmp_path, value):
    env = {"ARTICULATE_CONFIG_DIR": str(tmp_path), "ARTICULATE_HOUSE_VOICE": value}
    s = house_settings.resolve(environ=env)
    assert s["mode"] == "off" and s["sources"]["mode"] == "env"


def test_cli_off_and_on_write_the_settings_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("ARTICULATE_HOUSE_VOICE", raising=False)
    assert cli.main(["house", "off"]) == 0
    stored = json.loads((tmp_path / "house.json").read_text(encoding="utf-8"))
    assert stored["mode"] == "off"
    assert house_settings.resolve()["mode"] == "off"
    assert cli.main(["house", "on"]) == 0
    assert house_settings.resolve()["mode"] == "default"
    capsys.readouterr()


def test_env_overrides_the_file(tmp_path):
    (tmp_path / "house.json").write_text(json.dumps({"mode": "off"}), encoding="utf-8")
    env = {"ARTICULATE_CONFIG_DIR": str(tmp_path), "ARTICULATE_HOUSE_VOICE": "revise"}
    assert house_settings.resolve(environ=env)["mode"] == "revise"


def test_set_accepts_only_known_keys_and_values(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path))
    assert cli.main(["house", "set", "length=terse", "headings=never"]) == 0
    s = house_settings.resolve()
    assert s["tuning"]["length"] == "terse" and s["sources"]["length"] == "file"
    assert cli.main(["house", "set", "length=enormous"]) == 2
    assert cli.main(["house", "set", "voice=pirate"]) == 2
    capsys.readouterr()


def test_banned_tics_and_identity_are_not_tunable():
    with pytest.raises(ValueError):
        house_settings.validate({"mode": "default", "tuning": {"identity": "human"}})
    with pytest.raises(ValueError):
        house_settings.validate({"mode": "default", "tuning": {"banned_tics": "off"}})


def test_a_broken_settings_file_falls_back_to_defaults_with_a_note(tmp_path):
    (tmp_path / "house.json").write_text("{not json", encoding="utf-8")
    s = house_settings.resolve(environ={"ARTICULATE_CONFIG_DIR": str(tmp_path)})
    assert s["mode"] == house_settings.DEFAULT_MODE and s["problems"]


def test_show_prints_settings_sources_and_the_brief(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ARTICULATE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("ARTICULATE_HOUSE_VOICE", raising=False)
    assert cli.main(["house", "show"]) == 0
    out = capsys.readouterr().out
    assert "mode: off (default)" in out
    assert "The house voice is off; no brief is sent." in out


def test_resolution_reads_and_never_writes(tmp_path, monkeypatch):
    import builtins
    real = builtins.open

    def guard(file, mode="r", *a, **k):
        assert not set(mode) & set("wax+"), (file, mode)
        return real(file, mode, *a, **k)
    (tmp_path / "house.json").write_text(json.dumps({"mode": "brief"}), encoding="utf-8")
    monkeypatch.setattr(builtins, "open", guard)
    assert house_settings.resolve(environ={"ARTICULATE_CONFIG_DIR": str(tmp_path)})["mode"] == "brief"
