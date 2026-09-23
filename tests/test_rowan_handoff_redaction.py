"""What the handoff brief redacts, what it keeps, and how long that takes.

The brief is pasted into another provider's agent. These are the shapes a
recheck found passing through, the ordinary text each new pattern must leave
alone, and a time budget that fails if a pattern goes quadratic again.
"""
import json
import time

import pytest

from harness.rowan_handoff import DOES_NOT_PROVE
from harness.rowan_handoff_text import HOST_PATH, OMITTED, code, leaks, outbound, quote
from tests.test_rowan_handoff_safety import _brief, _records

SHAPES = [
    ("curl -u admin:Hunter2pass! https://api.example.test/v1", "Hunter2pass!"),
    ("curl --user 'admin:Hunter2 Zq9x' https://api.example.test", "Hunter2 Zq9x"),
    ("PGPASSWORD=Sup3rSecret psql -h db app", "Sup3rSecret"),
    ("docker login -u me -p dckr_pat_EXAMPLEonlyNotAToken0000 registry.example.test",
     "dckr_pat_EXAMPLEonlyNotAToken0000"),
    ("redis-cli -a S3cretRedisPw ping", "S3cretRedisPw"),
    ("The admin password is Hunter2pass! for now", "Hunter2pass!"),
    ("set DB_PASS=Tr0ub4dor&3", "Tr0ub4dor&3"),
    ("export MYSQL_PWD='Or4nge Jq7x'", "Or4nge Jq7x"),
    ("wget --http-password=Sup3rSecret https://files.example.test", "Sup3rSecret"),
    ("keytool -list -storepass Ch4ngeItNow", "Ch4ngeItNow"),
]


def _gone(secret, text):
    return all(part not in text for part in secret.split() if len(part) > 2)


@pytest.mark.parametrize("text,secret", SHAPES)
def test_each_shape_is_redacted_and_a_line_carrying_it_leaks(text, secret):
    for form in (text, json.dumps({"cmd": text})):
        out = outbound(form)
        assert _gone(secret, out) and OMITTED in out, out
        assert leaks(form), form
        assert not leaks(out), out


@pytest.mark.parametrize("path", [r"\\server\share\zain\file.txt",
                                  r"\\?\C:\Users\zain\notes.txt",
                                  r"\\wsl$\Ubuntu\home\zain\notes.txt"])
def test_unc_paths_are_host_paths(path):
    for form in (f"copy {path} here", json.dumps({"cmd": f"copy {path} here"})):
        out = outbound(form)
        assert "zain" not in out and "server" not in out, out
        assert HOST_PATH in out and out.startswith(form[:5]), out


KEPT = [
    "The token limit and the password field are unchanged.",
    "The password is required, and the api key is in the vault.",
    "docker run -u 1000:1000 -p 8080:80 app",
    "docker login -u me --password-stdin registry.example.test",
    "sudo -u www-data ls -a build",
    "git push -u origin main",
    "ssh -p 2222 deploy@example.test",
    "mysql -u root -p app",
    "psql --no-password -h db app",
    "proxy_bypass=true and tests_pass=12",
    "date -u +%H:%M",
    r"print('a\\nb') matches \\d+ digits",
]


@pytest.mark.parametrize("text", KEPT)
def test_ordinary_text_is_kept(text):
    assert outbound(text) == text
    assert not leaks(text)


def test_the_listed_shapes_do_not_reach_the_brief():
    ledger = [{"kind": "tool_call", "content": "run " + json.dumps({"cmd": text}), "meta": {}}
              for text, _ in SHAPES]
    progress = [{"type": "cli_tool_call", "call_id": "u", "tool": "Bash",
                 "arguments": {"command": r"type \\server\share\zain\file.txt"}}]
    final = "\n".join(text for text, _ in SHAPES)
    brief = _brief(_records(goal=SHAPES[5][0], ledger=ledger, progress=progress, final=final))
    for _, secret in SHAPES:
        assert _gone(secret, brief), secret
    assert "zain" not in brief
    # The list is still a list, and the response says so.
    assert "REDACTION_IS_PATTERN_BASED" in DOES_NOT_PROVE


def test_a_secret_across_the_cut_is_redacted_before_the_cut():
    # The shown part ends inside the value. Cutting before redacting would
    # leave "Hunte" with too few characters to look like a credential.
    text = "x" * 1_985 + " password Hunter2pass! and more"
    out = quote(text)
    assert "Hunte" not in out and "password [cred" in out
    assert "Hunte" not in code("y" * 185 + " password Hunter2pass!", limit=200)


def test_the_cut_counts_what_it_left_in_the_trace():
    out = quote("\n".join("z" * 3_000 for _ in range(70)), max_chars=8_000)
    assert out.count("\n> z") == 3
    assert out.endswith("[66 more lines and 202000 more characters are in the private trace]")


@pytest.mark.parametrize("unit", ["mysql ", "a-", "a.", "x://a:", "docker ", "-u a:",
                                  "redis-cli -a ", "the token is ", "PGPASSWORD",
                                  "password ", "\\\\a", "a_b_"])
def test_redaction_time_grows_with_the_text_not_its_square(unit):
    text = unit * (60_000 // len(unit))
    start = time.perf_counter()
    outbound(text)
    leaks(text[:2_000])
    # 1.2 MB in 20 lines: only what the quote can show is redacted.
    quote("\n".join([text] * 20), max_chars=40_000)
    assert time.perf_counter() - start < 2.0, unit
