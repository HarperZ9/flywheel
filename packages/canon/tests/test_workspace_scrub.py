"""The secret scrubber and the store's last check. Every value below is built at
run time so no committed line looks like a real credential."""
from __future__ import annotations

import io
import json

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_SECURITY
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.scrub import find_secrets, scrub, secrets_in
from canon.workspace.store import ProjectStore, SecretRefused

from ._workspace_helpers import init_repo

CASES = [
    ("anthropic-key", "key " + "sk-ant-api03-" + "a" * 30),
    ("openai-key", "key " + "sk-proj-" + "b" * 30),
    ("github-token", "token " + "ghp_" + "c" * 36),
    ("github-token", "token " + "github_pat_" + "d" * 30),
    ("gitlab-token", "token " + "glpat-" + "e" * 20),
    ("slack-token", "token " + "xoxb-" + "1" * 12 + "-abc"),
    ("aws-access-key", "id " + "AKIA" + "Z" * 16),
    ("google-api-key", "key " + "AIza" + "f" * 35),
    ("stripe-key", "key " + "sk_live_" + "g" * 24),
    ("huggingface-token", "token " + "hf_" + "h" * 34),
    ("npm-token", "token " + "npm_" + "i" * 36),
    ("jwt", "eyJ" + "j" * 12 + ".eyJ" + "k" * 12 + "." + "l" * 12),
    ("bearer-header", "Authorization: Bearer " + "m" * 20),
    ("api-key-header", "x-api-key: " + "n" * 20),
    ("connection-string", "postgres://app:" + "o" * 12 + "@db.example/app"),
    ("password-field", "Server=db;Password=" + "p" * 12 + ";"),
    ("json-secret", '{"client_secret": "' + "q" * 12 + '"}'),
    ("env-assignment", "export DEPLOY_TOKEN=" + "r" * 12),
    ("private-key", "-----BEGIN PRIVATE KEY-----\n" + "s" * 40 + "\n-----END PRIVATE KEY-----"),
]


@pytest.mark.parametrize("code, text", CASES)
def test_each_rule_redacts_its_shape_and_leaves_nothing_behind(code, text):
    result = scrub(text)
    assert f"[REDACTED:{code}]" in result.text
    assert result.hits.get(code, 0) >= 1
    assert find_secrets(result.text) == []
    assert scrub(result.text).text == result.text


@pytest.mark.parametrize("text", [
    "OPENAI_API_KEY=<your key here>",
    "GITHUB_TOKEN=${GITHUB_TOKEN}",
    "API_KEY=xxxx",
    "Set the PASSWORD variable before running the suite.",
    "The key idea is a strict prefix.",
    "https://github.com/example/repo.git",
    "RETRY_TOKEN_COUNT=5",
    '{"max_tokens": "512"}',
])
def test_placeholders_and_prose_are_left_alone(text):
    assert scrub(text).text == text
    assert find_secrets(text) == []


def test_an_unterminated_private_key_is_redacted_to_the_end():
    text = "note -----BEGIN RSA PRIVATE KEY-----\n" + "t" * 50
    assert scrub(text).text == "note [REDACTED:private-key]"


def test_secrets_in_walks_nested_values():
    value = {"a": ["fine", {"b": "ghp_" + "u" * 36}]}
    assert secrets_in(value) == ["github-token"]


def test_the_store_refuses_a_hand_written_secret(tmp_path):
    ident = derive_identity(init_repo(tmp_path / "r", "https://github.com/o/r"))
    store = ProjectStore(tmp_path / "s", ident)
    leaky = authoring.work_item(store, title="Use " + "sk-proj-" + "v" * 30 + " for CI")
    with pytest.raises(SecretRefused, match="openai-key"):
        store.put(leaky)
    assert store.records() == []


def test_the_cli_reports_a_refused_secret_with_the_security_code(tmp_path):
    repo = init_repo(tmp_path / "r", "https://github.com/o/r")
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(["--json", "workspace", "task", "rotate " + "ghp_" + "w" * 36,
                    "--workspace", str(repo), "--store", str(tmp_path / "s")],
                   stdin=None, stdout=stdout, stderr=stderr, environ={})
    assert code == EX_SECURITY
    payload = json.loads(stdout.getvalue())
    assert payload["failure_code"] == "secret_quarantine"
    assert "w" * 36 not in stdout.getvalue()


def test_a_secret_planted_in_a_store_file_by_hand_never_renders(tmp_path):
    from canon.workspace.brief import SecretInRender, make_brief
    from canon.workspace.pool import project_pool
    from canon.workspace.targets import target_for

    ident = derive_identity(init_repo(tmp_path / "r", "https://github.com/o/r"))
    store = ProjectStore(tmp_path / "s", ident)
    store.put(authoring.work_item(store, title="PLACEHOLDER"))
    path = store.project_dir() / "records.jsonl"
    canary = "ghp_" + "x" * 36
    path.write_text(path.read_text(encoding="utf-8").replace("PLACEHOLDER", canary),
                    encoding="utf-8")
    with pytest.raises(SecretInRender, match="github-token"):
        make_brief(ident, project_pool(store), target_for("codex"))
