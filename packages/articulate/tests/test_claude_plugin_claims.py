"""What the plugin's public words claim, held to what the plugin does.

A user reads the listing, the README, the privacy policy and the skill
description before deciding to check a confidential text, and Claude reads the
skill description in every session. These tests hold those words to the data
flow and to the result the tools return:

- The checker sends the text nowhere, and Claude still reads the text as part
  of the conversation. A paragraph that says the text stays local or goes
  nowhere must name the conversation.
- The README names every tool the plugin lists, and says which findings a check
  lists and which it only counts.
- A tool with no profile argument says it uses the default profile.
- Every link into this repository names a file that exists here, and the README
  gives the privacy policy's web address.

Each rule has a planted break, so a clean run is a finding about the words and
not a rule that never fires.
"""
import json
import re

from articulate import local_mcp, mcp_server
from claude_plugin_helpers import PLUGIN_ENV, ROOT, TEMPLATE, load

rules = load("claude_plugin_rules")

README = (TEMPLATE / "README.md").read_text(encoding="utf-8")
PLUGIN = json.loads((TEMPLATE / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
MARKET = json.loads((TEMPLATE / ".claude-plugin" / "marketplace.json")
                    .read_text(encoding="utf-8"))
DOCS = sorted(TEMPLATE.rglob("*.md")) + [ROOT / "docs" / "claude-plugin.md"]

STAYS_LOCAL = re.compile(
    r"(?i)\bstays? (?:on|in) (?:your|the user's|this) (?:machine|computer|device)"
    r"|\bstays? local\b|\bnever leaves?\b|\b(?:is|are) (?:not|never) sent\b"
    r"|\bsends? (?:the|your) text (?:nowhere|to no one|to nobody)"
    r"|\bnever sends? (?:the|your) text\b|\bsends? nothing\b")
CONVERSATION = re.compile(r"(?i)\bconversation\b")
REPO_FILE = re.compile(r"https://github\.com/HarperZ9/articulate/(?:blob|tree)/(?:main|release/0\.5\.x)/"
                       r"([^\s)\"'`<>]+)")


def _section(text, heading):
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def _paragraphs(text):
    return [p for p in re.split(r"\n[ \t]*\n", text) if p.strip()]


def _document_units():
    """(where, paragraph) for each listing string and each document paragraph."""
    units = [("plugin.json description", PLUGIN["description"]),
             ("marketplace.json description", MARKET["description"])]
    units += [("marketplace.json entry", e["description"]) for e in MARKET["plugins"]]
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        where = path.relative_to(ROOT).as_posix()
        front = rules.skill_front_matter(text)
        if front is not None:
            units.append((where + " description", front["description"]))
            text = text.split("\n---\n", 1)[1]
        units += [(where, p) for p in _paragraphs(text)]
    units += [("tool " + tool["name"], tool["description"]) for tool in local_mcp.TOOLS]
    return units


def _refusals(monkeypatch):
    """(where, message) for a hosted tool called under each way it is refused."""
    out = []
    for label, environ in (("plugin", PLUGIN_ENV),
                           ("local set only", {local_mcp.TOOLS_VAR: "local"}),
                           ("local-only switch only", {"ARTICULATE_LOCAL_ONLY": "1"})):
        for name in (local_mcp.TOOLS_VAR, "ARTICULATE_LOCAL_ONLY"):
            monkeypatch.delenv(name, raising=False)
        for name, value in environ.items():
            monkeypatch.setenv(name, value)
        for tool in ("fix", "judge", "polish"):
            result = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": tool,
                                                  "arguments": {"text": "A draft.", "backend": "anthropic"}}})
            assert result["result"].get("isError") is True, (label, tool, result)
            out.append((f"refusal of {tool} ({label})",
                        result["result"]["content"][0]["text"]))
    return out


def _unbounded(units):
    """Each unit that says the text stays local without naming the conversation."""
    return [(where, found.group(0)) for where, text in units
            for found in [STAYS_LOCAL.search(text)]
            if found and not CONVERSATION.search(text)]


def test_no_public_words_say_the_text_stays_local_without_the_conversation(monkeypatch):
    assert _unbounded(_document_units() + _refusals(monkeypatch)) == []


def test_an_unbounded_privacy_claim_is_caught():
    assert _unbounded([("planted", "Use it on drafts. The text stays on your machine.")])
    assert _unbounded([("planted", "Runs on the user's computer; the text is not sent "
                                   "anywhere.")])
    assert _unbounded([("planted", "It lists only the local tools, which never send the "
                                   "text anywhere.")])
    assert not _unbounded([("planted", "The checker sends the text nowhere; Claude reads "
                                       "the text as part of your conversation.")])


def _unnamed(listed, section):
    named = set(re.findall(r"`([^`]+)`", section))
    return sorted(set(listed) - named)


def test_the_readme_names_every_tool_the_plugin_lists():
    listed = [t["name"] for t in local_mcp.listed_tools(PLUGIN_ENV)]
    assert listed
    assert _unnamed(listed, _section(README, "What you get")) == []


def test_a_listed_tool_missing_from_the_readme_is_caught():
    assert _unnamed(["check", "compare"], _section(README, "What you get")) == ["compare"]


def _check_bullet():
    bullets = re.split(r"\n(?=- )", _section(README, "What you get"))
    return next(b for b in bullets if b.startswith("- `check`"))


def test_the_readme_says_which_findings_a_check_lists_and_which_it_counts():
    text = ("It is important to note that the plan works. By leveraging cutting-edge "
            "technology, teams move faster.\n")
    result = mcp_server.do_check(text, 50)
    assert result["advisory_count"] > 0 and result["hits"], "the case lost a tier"
    assert {h["tier"] for h in result["hits"]} <= {"HIGH", "MEDIUM"}
    bullet = " ".join(_check_bullet().split())
    assert "HIGH and MEDIUM" in bullet and "`advisory_count`" in bullet, bullet


def _profile_problem(description, schema):
    """A description that names a profile the tool gives the caller no way to pick."""
    if "profile" in schema["properties"]:
        return None
    for found in re.finditer(r"\bprofile\b", description):
        if not description[:found.start()].endswith("default "):
            return description[max(0, found.start() - 40):found.end()]
    return None


def test_a_tool_without_a_profile_argument_names_the_default_profile():
    for tool in local_mcp.TOOLS:
        assert _profile_problem(tool["description"], tool["inputSchema"]) is None, tool["name"]


def test_a_description_naming_an_unselectable_profile_is_caught():
    schema = {"properties": {"text": {"type": "string"}}}
    assert _profile_problem("whether it blocks under the profile", schema)
    assert not _profile_problem("whether it blocks under the default profile", schema)


def _missing_targets(text):
    return [path.rstrip(".,;:") for path in REPO_FILE.findall(text)
            if not (ROOT / path.rstrip(".,;:")).exists()]


def test_every_link_into_this_repository_names_a_file_here():
    sources = [TEMPLATE / ".claude-plugin" / "plugin.json",
               TEMPLATE / ".claude-plugin" / "marketplace.json"] + DOCS
    linked = 0
    for path in sources:
        text = path.read_text(encoding="utf-8")
        linked += len(REPO_FILE.findall(text))
        assert _missing_targets(text) == [], path.name
    assert linked >= 3, "the plugin no longer links its homepage and policy here"


def test_a_link_to_a_missing_file_is_caught():
    text = "See https://github.com/HarperZ9/articulate/blob/main/docs/nope.md."
    assert _missing_targets(text) == ["docs/nope.md"]


def test_the_readme_gives_the_privacy_policy_address():
    url = PLUGIN["privacyPolicyUrl"]
    assert url.startswith("https://")
    assert url in rules.policy_section(README)


def test_review_skill_matches_release_score_fields():
    review = (TEMPLATE / "skills" / "prose-review" / "SKILL.md").read_text(encoding="utf-8")
    result = mcp_server.do_score("A short draft.")
    for field in ("texture_score", "hard_hits", "advisories"):
        assert field in result and "`" + field + "`" in review
    assert "density per 1,000" not in review


def test_host_skill_uses_masked_protocol_and_reports_refusals():
    skill = (TEMPLATE / "skills" / "prose-edit" / "SKILL.md").read_text(encoding="utf-8")
    front = rules.skill_front_matter(skill)
    for name in ("edit_plan", "edit_submit"):
        assert f"`{name}`" in skill
    assert "allowed-tools" not in front
    assert "mcp__plugin_" not in skill
    for field in ("masked_text", "plan_id", "refused", "receipt.backend"):
        assert "`" + field + "`" in skill
    assert "exact original" in skill
    assert "Check-only fallback" in skill
    assert "check words and protected spans only" in skill
    assert "Meaning, quality, factual correctness and authorship stay with the reader" in skill


def test_release_line_link_to_missing_file_is_caught():
    text = "See https://github.com/HarperZ9/articulate/blob/release/0.5.x/docs/nope.md."
    assert _missing_targets(text) == ["docs/nope.md"]
