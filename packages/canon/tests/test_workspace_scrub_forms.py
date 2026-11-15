"""The everyday shapes of the secrets the scrubber promises to cover, and the
code and prose it must leave alone. Every value is built at run time, and the
end-to-end control runs import, accept and switch so it asserts on the files a
tool reads, not only on `scrub()`."""
from __future__ import annotations

import base64
import io
import json

import pytest

from canon.cli import run_cli
from canon.exit_codes import EX_OK
from canon.workspace import authoring
from canon.workspace.identity import derive_identity
from canon.workspace.import_write import import_session
from canon.workspace.scrub import find_secrets, scrub
from canon.workspace.store import ProjectStore, SecretRefused

from ._import_helpers import every_stored_byte
from ._workspace_helpers import init_repo

V = "canaryV4lue" + "Q7x9"


def _forms() -> list[str]:
    basic = base64.b64encode(("admin:" + V).encode()).decode()
    return [
        "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPx" + V,
        "db_password=" + V,
        'password = "' + V + '"',
        "password: " + V,
        "  redis_password: " + V,
        "DB_PASS=" + V,
        "SMTP_PASS=" + V,
        "export openai_api_key=" + V,
        "the password: hunter22",
        "Reset the password: " + "correcthorsebattery",
        "client_secret: " + V + "9f8e7d",
        "https://api.example.com/v1/items?access_token=" + V,
        "https://" + V + "abcdefgh@github.com/o/r.git",
        "postgres://app:ab/" + V + "@db.internal/app",
        "Authorization: Basic " + basic,
        "Cookie: sessionid=" + V + "; csrftoken=abc",
        "AccountName=a;AccountKey=" + V + "==;EndpointSuffix=core.windows.net",
        '{\\"password\\":\\"' + V + '\\"}',
        "-----BEGIN PGP PRIVATE KEY BLOCK-----\nlQOYB" + V + "\n-----END PGP PRIVATE KEY BLOCK-----",
        "PuTTY-User-Key-File-3: ssh-ed25519\nPrivate-Lines: 1\n" + V + "\nPrivate-MAC: ab12",
        "pypi-AgEIcHlwaS5vcmc" + V + "a" * 40,
        "https://hooks.slack.com/services/T0/B0/" + V,
        "https://discord.com/api/webhooks/123/" + V,
        "//registry.npmjs.org/:_authToken=" + V,
        "GOCSPX-" + V, "ya29." + V, "xapp-1-" + V, "whsec_" + V,
        "SG." + V + "." + V, "SK" + "0123456789abcdef" * 2, "dop_v1_" + "ab12" * 8,
        "shpat_" + "ab12" * 8, "123456789:AA" + V * 3,
        "AWS_CREDENTIALS=AKIA" + "CANARYAWSKEY0002" + ":" + V,
        "KEYS=" + "sk-proj-" + "q" * 24 + "," + V,
        "DB_PASSWORD=$" + V,
        "DB_PASSWORD=$2b$12$" + V,
        "ghp_" + V + "abcdefghijklmn",
        "sk-proj-WrapHead" + "1234",
    ]


@pytest.mark.parametrize("text", _forms())
def test_the_everyday_form_is_redacted_and_leaves_nothing_behind(text):
    result = scrub(text)
    assert result.hits, text
    assert V not in result.text and "WrapHead" not in result.text
    assert find_secrets(result.text) == []
    assert scrub(result.text).text == result.text


@pytest.mark.parametrize("text", [
    "sorted(rows, key=lambda r: r.id)",
    "token = get_token()",
    "token = tokens[0]",
    "password = self.password",
    "token: string",
    "bypass: true",
    "BYPASS_CACHE=true",
    "pip install hf_transfer",
    "echo $npm_lifecycle_event",
    "monkey = banana",
    "sort_key: name",
    "https://registry.npmjs.org:443/@scope/pkg",
    "password: $DB_PASSWORD",
    "GITHUB_TOKEN=${GITHUB_TOKEN:-unset}",
    "API_KEY=%API_KEY%",
    "passed: 1234 tests",
    "The password field is required.",
    "Fix token: expire it after an hour",
    "- [open] Refresh token: handle expiry (task-3)",
])
def test_code_and_prose_that_name_a_secret_stay_as_written(text):
    assert scrub(text).text == text
    assert find_secrets(text) == []


def test_the_store_refuses_a_hand_typed_lower_case_credential(tmp_path):
    ident = derive_identity(init_repo(tmp_path / "r", "https://github.com/o/r"))
    store = ProjectStore(tmp_path / "s", ident)
    with pytest.raises(SecretRefused):
        store.put(authoring.work_item(store, title="rotate db_password=" + V))


def _entry(text: str, repo, uid: str) -> dict:
    return {"type": "assistant", "sessionId": "0f8e2c1a-1b2c-4d5e-8f90-a1b2c3d4e5f6",
            "cwd": str(repo), "isSidechain": False, "uuid": uid,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def test_no_form_reaches_a_record_or_any_rendered_file(tmp_path):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/r")
    ident = derive_identity(repo)
    store = ProjectStore(tmp_path / "store", ident)
    texts = ["TODO: " + form.replace("\n", " ") for form in _forms()]
    texts.append("TODO: " + "y" * 166 + " ghp_" + "Cut" + V + "abcdefghijklmnop")
    texts.append("TODO: set OPENAI_API_KEY to sk-proj-WrapHead1234\n" + "Tail" * 10)
    path = tmp_path / "s.jsonl"
    path.write_text("".join(json.dumps(_entry(t, repo, f"a{n}")) + "\n"
                            for n, t in enumerate(texts)), encoding="utf-8")
    report = import_session(ident, store, str(path), source_format="claude-code")
    assert report["secrets_redacted"]
    for row in store.proposals():
        store.decide(row.record.id, accept=True, reason="test")
    base = ["--workspace", str(repo), "--store", str(store.root), "--home", str(tmp_path / "h")]
    for target in ("claude-code", "codex", "gemini-cli", "cursor", "copilot"):
        code = run_cli(["switch", "--to", target, "--create", *base], stdin=None,
                       stdout=io.StringIO(), stderr=io.StringIO(), environ={})
        assert code == EX_OK, target
    rendered = "\n".join(p.read_text(encoding="utf-8") for p in repo.rglob("*")
                         if p.is_file() and ".git" not in p.parts)
    haystack = every_stored_byte(store.root) + rendered + json.dumps(report)
    assert "[REDACTED:" in rendered
    assert V not in haystack and "WrapHead" not in haystack and "CutcanaryV4" not in haystack


def _import(tmp_path, texts):
    repo = init_repo(tmp_path / "repo", "https://github.com/o/r")
    ident = derive_identity(repo)
    store = ProjectStore(tmp_path / "store", ident)
    path = tmp_path / "s.jsonl"
    path.write_text("".join(json.dumps(_entry(t, repo, f"a{n}")) + "\n"
                            for n, t in enumerate(texts)), encoding="utf-8")
    report = import_session(ident, store, str(path), source_format="claude-code")
    return store, report


def test_a_token_whose_prefix_falls_outside_the_capture_window_is_still_redacted(tmp_path):
    tail = "Q" * 36
    store, report = _import(tmp_path, ["ghp_" + tail + " " + "x" * 170 + " did not work"])
    stored = (store.project_dir() / "proposed.jsonl").read_text(encoding="utf-8")
    assert "Q" * 20 not in stored
    assert report["secrets_redacted"].get("github-token") == 1


def test_a_token_cut_at_the_todo_cap_is_redacted_before_the_cut(tmp_path):
    token = "ghp_" + "abcdefghijklmnopqrstuvwxyz0123456789"
    store, report = _import(tmp_path, ["TODO: " + "y" * 191 + " " + token])
    stored = (store.project_dir() / "proposed.jsonl").read_text(encoding="utf-8")
    assert "ghp_abc" not in stored
    assert report["secrets_redacted"].get("github-token") == 1
