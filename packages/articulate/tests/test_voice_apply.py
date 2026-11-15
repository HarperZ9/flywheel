"""voice apply shapes the user's own draft toward their measured habits, only
when the user asks and attests the text is theirs. The plan binds the profile
hash, the meaning guard still holds, and the voice distances are reported and
never change what is accepted."""
import json

import pytest

from articulate import cli, host_edit, local_mcp, voice, voice_apply, voice_identity, voice_store
from voice_fixtures import SCAFFOLD_ESSAY, VARIED


@pytest.fixture
def store(tmp_path, monkeypatch):
    folder = tmp_path / "store"
    voice_identity.ensure_identity(folder)
    profile = voice_identity.bind(voice.build_profile([t for _, _, t in VARIED]), folder)
    voice_store.save(profile, "mine", folder)
    monkeypatch.setenv("ARTICULATE_VOICE_DIR", str(folder))
    return folder


def test_apply_without_the_attestation_is_refused(store):
    with pytest.raises(ValueError, match="yours"):
        voice_apply.plan(SCAFFOLD_ESSAY, "mine", authored_by_user=False, directory=store)
    with pytest.raises(ValueError):
        voice_apply.plan(SCAFFOLD_ESSAY, "mine", authored_by_user="yes", directory=store)


def test_mcp_plan_without_attestation_is_a_tool_error(store):
    r = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "voice_apply_plan", "arguments": {"text": SCAFFOLD_ESSAY, "voice_name": "mine"}}})
    assert r["result"]["isError"] is True


def test_v2_plan_binds_the_profile_hash_and_carries_a_voice_block(store):
    plan = voice_apply.plan(SCAFFOLD_ESSAY, "mine", authored_by_user=True, directory=store)
    settings = host_edit.plan_settings(SCAFFOLD_ESSAY, plan["plan_id"])
    assert settings["schema"] == "articulate/edit-plan/v2"
    assert settings["voice_profile_sha256"] == voice.sha256(voice.canonical(voice_store.load("mine", store)))
    assert settings["voice_name"] == "mine"
    assert "VOICE" in plan["instructions"] and "house voice does not apply" in plan["instructions"]
    assert "Never add" in plan["instructions"]


def test_a_v1_plan_still_verifies():
    import base64
    import hashlib
    text = "A short plain note."
    settings = {"schema": "articulate/edit-plan/v1", "mode": None, "profile": host_edit._settings(
        None, None, "fix", False, False)["profile"], "goal": "fix", "is_html": False, "is_tex": False,
        "ruleset": host_edit.detector.ruleset_fingerprint()}
    token = host_edit._token(text, settings)
    assert host_edit.plan_settings(text, token)["schema"] == "articulate/edit-plan/v1"
    _ = (base64, hashlib)


def test_a_changed_profile_after_planning_is_refused(store):
    plan = voice_apply.plan(SCAFFOLD_ESSAY, "mine", authored_by_user=True, directory=store)
    profile = voice_store.load("mine", store)
    profile["rhythm"]["sentence_cv"] = 0.01
    voice_store.save(profile, "mine", store)
    with pytest.raises(ValueError, match="profile changed"):
        voice_apply.submit(SCAFFOLD_ESSAY, SCAFFOLD_ESSAY, plan["plan_id"], directory=store)


def test_an_invented_anecdote_in_the_rewrite_is_retained(store):
    plan = voice_apply.plan(SCAFFOLD_ESSAY, "mine", authored_by_user=True, directory=store)
    paragraphs = SCAFFOLD_ESSAY.split("\n\n")
    paragraphs[3] = "I sat in the back row at that March meeting and watched them stall. " + paragraphs[3]
    rewrite = "\n\n".join(paragraphs)
    out = voice_apply.submit(SCAFFOLD_ESSAY, rewrite, plan["plan_id"], directory=store)
    assert "I sat in the back row" not in out["text"]
    assert any("added-first-person" in r["reasons"] for r in out["refused"])


def test_distances_are_reported_and_never_change_acceptance(store, monkeypatch):
    plan = voice_apply.plan(SCAFFOLD_ESSAY, "mine", authored_by_user=True, directory=store)
    rewrite = SCAFFOLD_ESSAY.replace("Residents asked", "People asked")
    first = voice_apply.submit(SCAFFOLD_ESSAY, rewrite, plan["plan_id"], directory=store)
    d = first["voice"]
    assert set(d) >= {"outside_before", "outside_after", "features", "scope"}
    assert not {"score", "distance", "total_distance"} & set(d)
    monkeypatch.setattr(voice, "compare", lambda *a, **k: {"features": [
        {"feature": "x", "verdict": "below"}] * 9, "locations": []})
    second = voice_apply.submit(SCAFFOLD_ESSAY, rewrite, plan["plan_id"], directory=store)
    assert first["text"] == second["text"] and first["refused"] == second["refused"]


def test_receipt_records_profile_hash_and_author_text_origin(store):
    answers = "I asked for those logs myself."
    plan = voice_apply.plan(SCAFFOLD_ESSAY, "mine", authored_by_user=True, directory=store,
                            author_text=answers)
    out = voice_apply.submit(SCAFFOLD_ESSAY, SCAFFOLD_ESSAY, plan["plan_id"], directory=store,
                             author_text=answers, author_text_origin="cli-file")
    rec = out["receipt"]
    assert rec["voice_profile_sha256"].startswith("sha256:")
    assert rec["author_text_origin"] == "cli-file"
    assert rec["author_text_sha256"].startswith("sha256:")


def test_cli_apply_needs_authored_by_me_and_writes_only_out(tmp_path, store, capsys):
    draft = tmp_path / "draft.md"
    draft.write_text(SCAFFOLD_ESSAY, encoding="utf-8")
    assert cli.main(["voice", "apply", str(draft), "--name", "mine", "--dir", str(store)]) == 2
    out = tmp_path / "plan.json"
    assert cli.main(["voice", "apply", str(draft), "--name", "mine", "--authored-by-me",
                     "--dir", str(store), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["plan_id"]
    assert draft.read_text(encoding="utf-8") == SCAFFOLD_ESSAY
    capsys.readouterr()


def test_mcp_plan_and_submit_round_trip(store):
    def call(name, args):
        r = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": args}})
        return r["result"]
    plan = json.loads(call("voice_apply_plan", {"text": SCAFFOLD_ESSAY, "voice_name": "mine",
                                                "authored_by_user": True})["content"][0]["text"])
    out = call("edit_submit", {"text": SCAFFOLD_ESSAY, "rewrite": SCAFFOLD_ESSAY,
                               "plan_id": plan["plan_id"]})
    payload = json.loads(out["content"][0]["text"])
    assert payload["receipt"]["voice_profile_sha256"].startswith("sha256:")
    assert payload["receipt"]["author_text_origin"] is None
