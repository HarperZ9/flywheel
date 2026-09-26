"""SP-39, A12: the gateway, not the file, decides what capture does. An
edited settings file is pending until the owner confirms it with presence;
the prompt hook says so; adoption writes a ledger entry and a witness
event."""
import json

import pytest

from capture_channel_fixture import prompt_event, run_hook, running_gateway
from harness import trace_capture_settings as settings
from harness.operation_grants import load_or_create_owner_ref
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_presence import PresenceError, confirm
from harness.trace_witness import MemorySink


def test_an_edited_file_is_not_in_effect_until_confirmed(tmp_path):
    owner = load_or_create_owner_ref(tmp_path)
    written = settings.write_file(tmp_path, {"content": "on"})
    effective = settings.effective(tmp_path, owner)
    assert effective["content"] == "off" and effective["pending_change"] is True
    sink = MemorySink()
    ref = confirm(tmp_path / "state", owner, "capture_settings", settings.digest(written),
                  "content on")
    settings.adopt(tmp_path, owner, ref, sink=sink)
    effective = settings.effective(tmp_path, owner)
    assert effective["content"] == "on" and effective["pending_change"] is False
    entry = CustodyLedger(tmp_path, owner).entries()[-1]
    assert entry["kind"] == "settings_adopted"
    assert entry["fields"]["settings"] == "capture"
    assert entry["fields"]["digest"] == settings.digest(written)
    assert "kind=settings_adopted" in sink.texts[-1]


def test_adoption_without_presence_or_for_another_digest_is_refused(tmp_path):
    owner = load_or_create_owner_ref(tmp_path)
    settings.write_file(tmp_path, {"content": "on"})
    with pytest.raises(PresenceError):
        settings.adopt(tmp_path, owner, None, sink=MemorySink())
    other = confirm(tmp_path / "state", owner, "capture_settings", "e" * 64, "x")
    with pytest.raises(PresenceError):
        settings.adopt(tmp_path, owner, other, sink=MemorySink())
    assert settings.effective(tmp_path, owner)["content"] == "off"


def test_a_switch_whose_feature_is_not_built_accepts_only_off(tmp_path):
    with pytest.raises(ValueError):
        settings.write_file(tmp_path, {"archive_transcripts": "on"})


def test_a_malformed_file_changes_nothing_and_is_reported(tmp_path):
    owner = load_or_create_owner_ref(tmp_path)
    (tmp_path / settings.FILENAME).write_text('{"content": "maybe"}')
    effective = settings.effective(tmp_path, owner)
    assert effective["content"] == "off" and effective["pending_change"] is True
    assert effective["file_valid"] is False


def test_the_prompt_hook_shows_the_pending_notice(tmp_path, monkeypatch):
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    with running_gateway(home, monkeypatch):
        settings.write_file(home, {"content": "on"})
        proc = run_hook(home, "prompt", prompt_event(), cwd=work)
    assert proc.returncode == 0
    message = json.loads(proc.stdout)["systemMessage"]
    assert "settings changed on disk and are not in effect" in message
    assert "flywheel traces capture confirm" in message
