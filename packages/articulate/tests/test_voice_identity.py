"""The personal profile belongs to one local identity. It is made only from
text the user names and attests is theirs, it stays in the local store, it
exports and imports under the same owner, and it deletes cleanly."""
import json

import pytest

from articulate import cli, voice, voice_identity, voice_store
from voice_fixtures import SCAFFOLD_ESSAY, VARIED


def _samples(tmp_path):
    paths = []
    for name, _, text in VARIED:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        paths.append(str(p))
    return paths


def _learn(tmp_path, store, name="mine", extra=()):
    return cli.main(["voice", "learn", *_samples(tmp_path), "--name", name, "--mine",
                     "--dir", str(store), *extra])


def test_learn_without_the_mine_attestation_stops(tmp_path, capsys):
    store = tmp_path / "store"
    assert cli.main(["voice", "learn", *_samples(tmp_path), "--name", "x", "--dir", str(store)]) == 2
    assert "--mine" in capsys.readouterr().err
    assert not store.exists()


def test_learn_binds_owner_and_attestation(tmp_path, capsys):
    store = tmp_path / "store"
    assert _learn(tmp_path, store) == 0
    ident = voice_identity.load_identity(store)
    profile = voice_store.load("mine", store)
    assert profile["owner"]["owner_id"] == ident["owner_id"]
    assert profile["attestation"]["mine"] is True and profile["attestation"]["at"]
    capsys.readouterr()


def test_profile_holds_no_sample_sentence(tmp_path, capsys):
    store = tmp_path / "store"
    _learn(tmp_path, store)
    raw = (store / "mine.json").read_text(encoding="utf-8")
    from articulate.authorship import sentences
    for _, _, text in VARIED:
        for s in sentences(text):
            if len(s.split()) >= 4:
                assert s not in raw, s
    for name in ("Doreen", "Luis", "Gerald", "Fife", "Olympia"):
        assert name not in raw
    capsys.readouterr()


def test_profile_is_created_only_from_named_files(tmp_path, capsys, monkeypatch):
    import builtins
    store = tmp_path / "store"
    samples = _samples(tmp_path)
    real = builtins.open
    read = []

    def spy(file, mode="r", *a, **k):
        if "r" in mode and "+" not in mode:
            read.append(str(file))
        return real(file, mode, *a, **k)
    monkeypatch.setattr(builtins, "open", spy)
    assert cli.main(["voice", "learn", *samples, "--name", "mine", "--mine", "--dir", str(store)]) == 0
    monkeypatch.setattr(builtins, "open", real)
    user_reads = {r for r in read if not r.endswith(".py") and str(store) not in r}
    assert user_reads == set(samples)
    capsys.readouterr()


def test_a_foreign_owner_is_refused_in_compare_and_apply(tmp_path, capsys):
    store = tmp_path / "store"
    _learn(tmp_path, store)
    profile = voice_store.load("mine", store)
    profile["owner"]["owner_id"] = "someone-else"
    voice_store.save(profile, "theirs", store)
    with pytest.raises(ValueError, match="owner"):
        voice_identity.check_owner(profile, store)
    draft = tmp_path / "d.md"
    draft.write_text(SCAFFOLD_ESSAY, encoding="utf-8")
    assert cli.main(["voice", "compare", str(draft), "--name", "theirs", "--dir", str(store)]) == 2
    assert cli.main(["voice", "apply", str(draft), "--name", "theirs", "--authored-by-me",
                     "--dir", str(store)]) == 2
    assert "owner" in capsys.readouterr().err


def test_export_import_round_trip_and_adopt_only_on_an_empty_store(tmp_path, capsys):
    store, other, third = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    _learn(tmp_path, store)
    out = tmp_path / "export.json"
    assert cli.main(["voice", "export", "mine", "--out", str(out), "--dir", str(store)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == "articulate/voice-export/v1" and data["profile_sha256"].startswith("sha256:")
    assert cli.main(["voice", "import", str(out), "--dir", str(other)]) == 2
    assert cli.main(["voice", "import", str(out), "--adopt-identity", "--dir", str(other)]) == 0
    assert voice_store.load("mine", other) == voice_store.load("mine", store)
    assert voice_identity.load_identity(other)["owner_id"] == voice_identity.load_identity(store)["owner_id"]
    voice_identity.ensure_identity(third)
    assert cli.main(["voice", "import", str(out), "--adopt-identity", "--dir", str(third)]) == 2
    capsys.readouterr()


def test_a_tampered_export_is_refused(tmp_path, capsys):
    store, other = tmp_path / "a", tmp_path / "b"
    _learn(tmp_path, store)
    out = tmp_path / "export.json"
    cli.main(["voice", "export", "mine", "--out", str(out), "--dir", str(store)])
    data = json.loads(out.read_text(encoding="utf-8"))
    data["profile"]["rhythm"]["sentence_cv"] = 9.9
    out.write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["voice", "import", str(out), "--adopt-identity", "--dir", str(other)]) == 2
    capsys.readouterr()


def test_delete_all_leaves_no_file(tmp_path, capsys):
    store = tmp_path / "store"
    _learn(tmp_path, store)
    _learn(tmp_path, store, "second")
    assert cli.main(["voice", "delete", "--all", "--dir", str(store)]) == 0
    printed = capsys.readouterr().out
    assert "mine.json" in printed and "identity.json" in printed
    assert not store.exists() or list(store.iterdir()) == []


def test_delete_one_keeps_the_others(tmp_path, capsys):
    store = tmp_path / "store"
    _learn(tmp_path, store)
    _learn(tmp_path, store, "second")
    assert cli.main(["voice", "delete", "mine", "--dir", str(store)]) == 0
    assert voice_store.names(store) == ["second"]
    capsys.readouterr()


def test_identity_command_shows_and_sets_a_display_name(tmp_path, capsys):
    store = tmp_path / "store"
    assert cli.main(["voice", "identity", "--name", "Sam", "--dir", str(store)]) == 0
    assert voice_identity.load_identity(store)["display_name"] == "Sam"
    assert cli.main(["voice", "identity", "--dir", str(store)]) == 0
    assert "Sam" in capsys.readouterr().out


def test_no_mcp_tool_learns_exports_imports_or_deletes():
    from articulate import local_mcp
    names = {t["name"] for t in local_mcp.TOOLS}
    for bad in ("voice_learn", "voice_export", "voice_import", "voice_delete"):
        assert bad not in names


def test_store_gitignore_is_written_with_the_identity(tmp_path):
    voice_identity.ensure_identity(tmp_path / "s")
    assert (tmp_path / "s" / ".gitignore").read_text(encoding="utf-8").strip() == "*"


def test_compare_runs_on_an_owned_profile(tmp_path):
    store = tmp_path / "store"
    voice_identity.ensure_identity(store)
    p = voice.build_profile([t for _, _, t in VARIED])
    owned = voice_identity.bind(p, store)
    voice_store.save(owned, "mine", store)
    voice_identity.check_owner(voice_store.load("mine", store), store)
