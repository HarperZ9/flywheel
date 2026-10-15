"""Falsifiers for skills and the web_fetch tool in `flywheel code`."""
import io
import json

from harness.code_session import web
from harness.code_session.backends import build_agent
from harness.code_session.rules import Rules
from harness.code_session.session import new_session
from harness.code_session.skills import load_skills
from tests.test_code_session import ScriptBackend, _bare_runner


def _skill(folder, name, desc, body):
    d = folder / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n{body}",
                                encoding="utf-8")


def test_skills_list_names_only_and_load_on_demand(tmp_path):
    _skill(tmp_path / ".flywheel" / "skills", "release", "cut a release", "Step 1: bump.")
    _skill(tmp_path / ".claude" / "skills", "review", "review a diff", "Read every hunk.")
    skills = load_skills(str(tmp_path), None)
    assert sorted(skills) == ["release", "review"]
    s = new_session(build_agent([ScriptBackend(['TOOL skill {"name": "release"}', "bumped"])]),
                    str(tmp_path), mode="plan", runner=_bare_runner)
    s.set_skills(skills)
    assert "- release: cut a release" in s.agent.system
    assert "Step 1: bump." not in s.agent.system
    s.turn("release it")
    result = [e.content for e in s.ledger.entries if e.kind == "tool_result"][0]
    assert "Step 1: bump." in result


def test_unknown_skill_is_an_error_result(tmp_path):
    s = new_session(build_agent([ScriptBackend([])]), str(tmp_path), mode="auto")
    res = s.executor.execute("skill", {"name": "nope"})
    assert not res.ok and "no skill named" in res.output


class FakeResp(io.BytesIO):
    def __init__(self, body, ctype="text/html", status=200):
        super().__init__(body)
        self.status = status
        self.headers = {"Content-Type": ctype}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_turns_html_into_text_and_records_the_hash():
    page = b"<html><script>evil()</script><h1>Title</h1><p>Body &amp; more</p></html>"
    ok, out = web.fetch("https://example.org/", opener=lambda req, timeout: FakeResp(page))
    assert ok and "Title" in out and "Body & more" in out and "evil" not in out
    import hashlib
    assert hashlib.sha256(page).hexdigest() in out


def test_fetch_refuses_plain_http_and_other_schemes():
    for url in ("http://example.org/", "file:///etc/passwd", "ftp://x/"):
        ok, out = web.fetch(url, opener=lambda *a, **k: (_ for _ in ()).throw(AssertionError))
        assert not ok and out.startswith("[refused]")
    assert web.check_url("http://127.0.0.1:8000/") is None


def test_web_fetch_is_refused_in_plan_mode_and_asks_in_ask_mode(tmp_path):
    asked = []
    s = new_session(build_agent([ScriptBackend(['TOOL web_fetch {"url": "https://x.org"}', "k"])]),
                    str(tmp_path), mode="ask", approver=lambda n, a: asked.append(n) or "no")
    s.turn("look it up")
    assert asked == ["web_fetch"]
    p = new_session(build_agent([ScriptBackend(['TOOL web_fetch {"url": "https://x.org"}', "k"])]),
                    str(tmp_path), mode="plan")
    p.turn("look it up")
    decision = [json.loads(e.content) for e in p.ledger.entries if e.kind == "approval"][0]
    assert decision["decision"] == "deny" and decision["class"] == "network"


def test_rules_match_web_fetch_urls(tmp_path):
    s = new_session(build_agent([ScriptBackend(['TOOL web_fetch {"url": "https://evil.example/x"}',
                                                "k"])]), str(tmp_path), mode="auto")
    s.set_rules(Rules(deny=["web_fetch:https://evil.example/*"]))
    s.turn("fetch")
    result = [e.content for e in s.ledger.entries if e.kind == "tool_result"][0]
    assert result.startswith("[denied] a permission rule refuses")
