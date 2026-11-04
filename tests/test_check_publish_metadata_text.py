"""check_publish_metadata: text, fetch-code, deny-list and git checks.

Leak strings are built at run time so this file does not itself carry them.
"""
import importlib.util
import io
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location(
    "check_publish_metadata", ROOT / "scripts" / "check_publish_metadata.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
T = C.T

USER_PATH = "C:" + "\\" + "Users" + "\\" + "Zain" + "\\notes.txt"
DEV_PATH = "c:" + "/" + "dev" + "/" + "public/x"
JSON_PATH = '"C:' + "\\\\" + "dev" + "\\\\" + 'tool"'
ADDR = "someone" + "@" + "gmail.com"


def cats(text, suffix=".md", patterns=None):
    return sorted({c for _l, c, _d in T.check_text(text, suffix, patterns or T.GENERIC)})


def test_local_paths_found_in_every_separator_form():
    assert cats(USER_PATH) == ["local-path"]
    assert cats(DEV_PATH) == ["local-path"]
    assert cats(JSON_PATH) == ["local-path"]
    assert cats("see /usr/share/dev/ and D:/data") == []


def test_consumer_address_found_and_example_address_ignored():
    assert cats("contact " + ADDR) == ["personal-email"]
    assert cats("contact someone@example.org") == []


def test_fetch_code_with_address_in_user_agent_or_mailto_fails():
    ua = 'UA = {"User-Agent": "tool/1.0 (mailto:' + "lab" + "@" + 'uni.edu)"}'
    q = 'u = base + "?rows=2&mailto=' + "lab" + "@" + 'uni.edu"'
    kw = 'urlencode(dict(q=1, mailto="' + "lab" + "@" + 'uni.edu"))'
    ncbi = 'urlencode(dict(db="pubmed", email="' + "lab" + "@" + 'uni.edu"))'
    for line in (ua, q, kw, ncbi):
        assert cats(line, ".py") == ["fetch-header"], line


def test_fetch_rule_ignores_links_noreply_and_non_code():
    link = 'href="mailto:' + "lab" + "@" + 'uni.edu"'
    assert cats(link, ".js") == []
    assert cats('UA = "tool/1.0 (mailto:someone@example.com)"', ".py") == []
    assert cats('UA = "tool/1.0 (mailto:' + "lab" + "@" + 'uni.edu)"', ".md") == []
    assert cats('UA = "research-fetch/1.0"', ".py") == []
    assert cats('    "email": "' + "lab" + "@" + 'uni.edu",', ".py") == []
    assert cats('UA = "tool/1.0 (mailto:bot@ci.invalid)"', ".py") == []


def test_deny_list_entries_match_and_values_never_print(tmp_path, monkeypatch):
    secret = "Tailnet" + "Example42"
    deny = tmp_path / "deny.txt"
    deny.write_text("# private names\n" + secret + "\n", encoding="utf-8")
    site = tmp_path / "site"
    site.mkdir()
    (site / "page.html").write_text("<p>host " + secret.lower() + ".ts.net</p>", encoding="utf-8")
    monkeypatch.setattr(T, "_git", lambda args, cwd=None: None)
    out = io.StringIO()
    code, res = C.run([str(site)], mode="fail", git="none", deny_list=str(deny), stream=out)
    assert code == 1
    assert res["roots"][0]["findings"] == {"deny-list": 1}
    assert "deny list entry 2" in out.getvalue()
    assert secret.lower() not in out.getvalue().lower()


def test_machine_name_comes_from_the_running_host(monkeypatch):
    monkeypatch.setenv("COMPUTERNAME", "WORKSTATION" + "7781")
    monkeypatch.setattr(T, "_git", lambda args, cwd=None: None)
    pats = T.local_patterns(None)
    assert cats("built on workstation7781", patterns=pats) == ["machine-name"]


def test_allow_file_skips_fixture_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "_git", lambda args, cwd=None: None)
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "path.txt").write_text(USER_PATH, encoding="utf-8")
    (tmp_path / "doc.md").write_text(USER_PATH, encoding="utf-8")
    (tmp_path / ".publish-metadata-allow").write_text("fixtures/*\n", encoding="utf-8")
    code, res = C.run([str(tmp_path)], mode="fail", git="none", stream=io.StringIO())
    assert code == 1 and res["roots"][0]["files_with_findings"] == 1


def _git(repo, *args, env=None):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                   env={**os.environ, **(env or {})})


def test_git_author_email_and_offset_warned_not_failed(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.txt").write_text("clean\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    env = {"GIT_AUTHOR_NAME": "A", "GIT_AUTHOR_EMAIL": ADDR, "GIT_COMMITTER_NAME": "A",
           "GIT_COMMITTER_EMAIL": ADDR, "GIT_AUTHOR_DATE": "2026-01-02T03:04:05-0700",
           "GIT_COMMITTER_DATE": "2026-01-02T03:04:05-0700"}
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x", env=env)
    found = T.check_git(repo, "all")
    assert ("git-timezone", "offset -0700 on 1 commits") in found
    assert any(c == "git-author" for c, _d in found)
    assert all(ADDR not in d for _c, d in found)
    out = io.StringIO()
    code, res = C.run([str(repo)], mode="fail", git="all", stream=out)
    assert code == 0, "git findings warn and do not fail"
    assert res["roots"][0]["files_scanned"] == 1


def test_untracked_files_are_skipped_in_a_checkout(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "kept.md").write_text("clean\n", encoding="utf-8")
    (repo / "scratch.md").write_text(USER_PATH, encoding="utf-8")
    _git(repo, "add", "kept.md")
    code, res = C.run([str(repo)], mode="fail", git="none", stream=io.StringIO())
    assert code == 0 and res["roots"][0]["files_scanned"] == 1
    code, _res = C.run([str(repo)], mode="fail", git="none", all_files=True, stream=io.StringIO())
    assert code == 1
