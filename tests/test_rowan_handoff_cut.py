"""A credential the brief's cut splits is still replaced whole.

Each field is redacted whole before it is cut. A quote reads whole lines, so
no credential is split before the patterns run, and a field longer than the
brief redacts stays in the private trace instead of being read in part. These
tests walk the cut through a credential, from one character before it to one
past it, including a token far longer than any fixed read-ahead margin.
"""
import pytest

from harness.rowan_handoff_text import (OMITTED, REDACT_CHARS, code, flat_line, outbound,
                                       quote)
from tests.test_rowan_handoff_safety import _brief, _records

SECRET = "Zq9xWv7Tk3Jm"
TOKEN = "eyJ" + "Qx7Vb3Zk" * 150
SHORT_URL = f"https://admin:{SECRET}@db.internal/api"
LONG_URL = f"https://oauth2:{TOKEN}@gitlab.example.test/team/app.git"
CASES = [(SHORT_URL, SECRET), (LONG_URL, TOKEN)]


def _shows_part(secret: str, text: str) -> bool:
    return any(secret[i:i + 4] in text for i in range(len(secret) - 3))


def _offsets(secret: str) -> list[int]:
    """Where the cut falls, counted from the credential's first character."""
    ends = [*range(-1, 24), *range(len(secret) - 24, len(secret) + 2)]
    return sorted(set(ends) | set(range(0, len(secret), 13)))


@pytest.mark.parametrize("url,secret", CASES, ids=["short", "long"])
def test_every_cut_through_a_credential_in_a_field_shows_none_of_it(url, secret):
    text = "git clone " + url
    start = text.index(secret)
    for offset in _offsets(secret):
        # code() shows limit - 3 characters of the line, then "...".
        shown = code(text, limit=start + offset + 3)
        assert not _shows_part(secret, shown), (offset, shown)


@pytest.mark.parametrize("url,secret", CASES, ids=["short", "long"])
def test_every_cut_through_a_credential_in_a_quote_shows_none_of_it(url, secret):
    line = "k" * 50 + " " + url
    start = line.index(secret)
    for offset in _offsets(secret):
        # The line cut: each quoted line shows at most line_chars characters.
        assert not _shows_part(secret, quote(line, line_chars=start + offset)), offset
        # The quote cut: the last line gets what is left of max_chars.
        lines = "\n".join(["m" * 150] * 4 + [line])
        assert not _shows_part(secret, quote(lines, max_chars=600 + start + offset)), offset


def test_a_long_token_across_the_cut_does_not_reach_the_brief():
    command = "git clone " + "k" * 20 + " " + LONG_URL
    goal = "x" * 1_900 + " " + LONG_URL
    brief = _brief(_records(goal=goal, final=goal, progress=[
        {"type": "cli_tool_call", "call_id": "u", "tool": "Bash",
         "arguments": {"command": command}}]))
    assert not _shows_part(TOKEN, brief)
    assert brief.count(f"https://{OMITTED}@gitlab.example.test/team/app.git") == 3


def test_the_shown_part_is_the_head_of_the_whole_redaction():
    # An earlier credential redacts to a marker far shorter than itself, so a
    # window read a fixed margin past the cut would run out before the room.
    text = 'curl -H "Authorization: Bearer ' + TOKEN + '" ' + "k" * 200 + " " + LONG_URL
    assert code(text, limit=160) == "`" + outbound(text)[:157] + "...`"
    lines = [f"File C:/Users/zain/AppData/pkg/pool_{n:03d}.py, line 1" for n in range(54)]
    red = outbound("\n".join(lines + [text])).split("\n")
    assert quote("\n".join(lines + [text])).split("\n") == ["> " + line for line in red]


def test_a_line_bound_pattern_still_sees_its_line_in_a_one_line_field():
    # htpasswd's password is the last argument of its line. Flattening the
    # lines before redacting made it the middle of one long line, and kept it.
    command = f"htpasswd -b .htpasswd admin {SECRET}\nnginx -s reload -q"
    reply = f"Set it with:\nhtpasswd -b .htpasswd admin {SECRET}\nthen ran it with --verbose"
    assert SECRET not in flat_line(reply) and SECRET not in code(command)
    brief = _brief(_records(
        ledger=[{"kind": "assistant", "content": reply, "meta": {}}],
        progress=[{"type": "cli_tool_call", "call_id": "u", "tool": "Bash",
                   "arguments": {"command": command}}]))
    assert SECRET not in brief
    assert f"htpasswd -b .htpasswd admin {OMITTED} nginx -s reload -q" in brief


def test_a_private_key_the_line_cap_splits_is_still_redacted():
    body = ["MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" + f"{n:032d}" for n in range(20)]
    key = ["-----BEGIN PRIVATE KEY-----", *body, "-----END PRIVATE KEY-----"]
    out = quote("\n".join([f"note {n}" for n in range(50)] + key))
    assert "MIIEvQ" not in out and "BEGIN PRIVATE" not in out
    assert out.count(OMITTED) == 10


def test_a_field_longer_than_the_brief_redacts_stays_in_the_trace():
    text = f"password {SECRET} " + "y" * REDACT_CHARS
    for shown in (flat_line(text, limit=80), code(text, limit=160)):
        assert SECRET not in shown and "yyyy" not in shown
        assert "characters left in the private trace" in shown, shown
    # A quote reads whole lines up to the bound, and counts the rest.
    out = quote("\n".join(["first line", text, "last line"]))
    assert out.splitlines() == [
        "> first line",
        f"> [2 more lines and {len(text) + len('last line')} more characters are in "
        "the private trace]"]
    brief = _brief(_records(goal=text, final=text))
    assert SECRET not in brief and "yyyy" not in brief and len(brief) < 20_000


def test_the_doc_states_the_bound_the_code_reads():
    from pathlib import Path
    doc = " ".join((Path(__file__).resolve().parents[1] / "docs" / "ROWAN-HANDOFF.md")
                   .read_text(encoding="utf-8").split())
    assert f"No field reads more than {REDACT_CHARS:,} characters" in doc


def test_only_the_listed_commands_and_steps_are_read(monkeypatch):
    # Each field may read up to REDACT_CHARS, so the brief reads only the
    # entries it lists and counts the rest.
    import harness.rowan_handoff_text as text
    real, read = text.outbound, []
    monkeypatch.setattr(text, "outbound",
                        lambda value, root=None: read.append(value) or real(value, root))
    progress = [{"type": "cli_tool_call", "call_id": f"u{i}", "tool": "Bash",
                 "arguments": {"command": f"echo {i}"}} for i in range(30)]
    progress += [{"type": "cli_message", "text": f"step {i}"} for i in range(30)]
    progress.append({"type": "cli_message", "text": " \n "})
    brief = _brief(_records(progress=progress))
    for title in ("Commands run", "Steps the model stated"):
        section = brief[brief.index(f"## {title}"):]
        assert section.split("\n## ")[0].rstrip().endswith("- and 10 more in the trace")
    assert "echo 19" in read and "step 19" in read
    assert "echo 20" not in read and "step 20" not in read
