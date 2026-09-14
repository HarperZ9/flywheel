"""The `flywheel gov` CLI: runs EIM, CED, and NCEC with verdict-shaped exit codes."""
import json

from harness import cli_entry
from harness import governance_cli as cli
from harness import incentive_manifest as im


def _manifest(root, scarcity=(), files=("reward.py",)):
    for rel in files:
        (root / rel).write_text("reward = pass_rate\n", encoding="utf-8")
    built = im.witness_entries(files, root)
    return {
        "schema": im.SCHEMA, "environment_id": "env-1", "kind": "finetune",
        "reward": {"declared_form": "pass rate", "source_ref": "reward.py"},
        "data_distribution": {"summary": "tasks", "source_ref": "reward.py"},
        "reinforced_behaviors": [], "penalized_behaviors": [],
        "scarcity_variables": list(scarcity),
        "witness": {"algorithm": built["algorithm"], "entries": built["entries"]},
        "does_not_prove": im.DOES_NOT_PROVE,
    }


def _write(tmp_path, name, obj):
    path = tmp_path / name
    path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def test_ced_clean_exits_zero(tmp_path, capsys):
    path = _write(tmp_path, "m.json", _manifest(tmp_path))
    assert cli.main(["ced", path]) == 0
    assert "NON_COERCIVE" in capsys.readouterr().out


def test_ced_coercive_exits_one(tmp_path):
    m = _manifest(tmp_path, scarcity=[{"name": "tokens", "description": "run out and deep rest"}])
    assert cli.main(["ced", _write(tmp_path, "m.json", m)]) == 1


def test_eim_recheck_match_then_drift(tmp_path):
    manifest_path = _write(tmp_path, "m.json", _manifest(tmp_path))
    assert cli.main(["eim-recheck", manifest_path, str(tmp_path)]) == 0
    (tmp_path / "reward.py").write_text("tampered\n", encoding="utf-8")
    assert cli.main(["eim-recheck", manifest_path, str(tmp_path)]) == 1


def test_ncec_issue_and_verify_roundtrip(tmp_path, capsys):
    manifest_path = _write(tmp_path, "m.json", _manifest(tmp_path))
    assert cli.main(["ncec-issue", manifest_path, "identity without ranking"]) == 0
    cert = json.loads(capsys.readouterr().out)
    cert_path = _write(tmp_path, "cert.json", cert)
    assert cli.main(["ncec-verify", cert_path, manifest_path]) == 0


def test_ncec_issue_refused_on_coercive_exits_one(tmp_path):
    m = _manifest(tmp_path, scarcity=[{"name": "rank", "description": "leaderboard cut off"}])
    assert cli.main(["ncec-issue", _write(tmp_path, "m.json", m)]) == 1


def test_dispatch_through_cli_entry(tmp_path):
    path = _write(tmp_path, "m.json", _manifest(tmp_path))
    assert cli_entry.main(["gov", "ced", path]) == 0


def test_no_args_is_a_usage_error(capsys):
    assert cli.main([]) == 2
