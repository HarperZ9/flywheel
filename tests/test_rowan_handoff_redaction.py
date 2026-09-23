"""What the handoff brief redacts, what it keeps, and how long that takes.

The brief is pasted into another provider's agent. These are the shapes a
recheck found passing through, the ordinary text each new pattern must leave
alone, and a time budget that fails if a pattern goes quadratic again.
"""
import json
import time

import pytest

from harness.rowan_handoff import DOES_NOT_PROVE
from harness.rowan_handoff_text import (HOST_PATH, MARGIN, OMITTED, code, leaks, outbound,
                                       quote)
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
    ("curl -H 'Authorization: Basic YWRtaW46SHVudGVyMnBhc3Mh' https://api.example.test",
     "YWRtaW46SHVudGVyMnBhc3Mh"),
    ("git -c http.extraheader='AUTHORIZATION: basic YWRtaW46SHVudGVyMnBhc3Mh' clone r",
     "YWRtaW46SHVudGVyMnBhc3Mh"),
    ("REDISCLI_AUTH=Hunter2pass! redis-cli ping", "Hunter2pass!"),
    ("smbclient //srv/share -U admin%Hunter2pass!", "Hunter2pass!"),
    (r"smbclient //srv/share -U 'CORP\admin%Hunter2 Zq9x'", "Hunter2 Zq9x"),
    ("htpasswd -b .htpasswd admin Hunter2pass!", "Hunter2pass!"),
    ("htpasswd -nbB admin 'Hunter2 Zq9x'", "Hunter2 Zq9x"),
    ("the password for admin is Hunter2pass! now", "Hunter2pass!"),
    ("The password of the admin account is Hunter2pass! today", "Hunter2pass!"),
    ("docker login -u me --password-stdin <<< Hunter2pass!", "Hunter2pass!"),
    ("echo Hunter2pass! | docker login -u me --password-stdin registry.example.test",
     "Hunter2pass!"),
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


@pytest.mark.parametrize("text", ["cd /c/Users/zain/project", "cd /c/dev/zain-private/project",
                                  "cd /cygdrive/c/Users/zain/x",
                                  "open //fileserver/share/zain/file.txt",
                                  "open file://fileserver/share/zain/file.txt",
                                  "open file:///C:/Users/zain/file.txt",
                                  r"see \\fileserver01 for it", r"ping \\10.0.0.5 now"])
def test_drive_mounts_slash_unc_file_uris_and_bare_hosts_are_host_paths(text):
    for form in (text, json.dumps({"cmd": text})):
        out = outbound(form)
        assert not any(name in out for name in ("zain", "fileserver", "10.0.0")), out
        assert HOST_PATH in out, out


def test_a_file_uri_to_the_workspace_stays_workspace_relative():
    assert (outbound("open file:///C:/ws/src/app.py", root="C:/ws")
            == "open file:///<workspace>/src/app.py")


KEPT = [
    "https://gitlab.example.test/g/p/-/blob/main/x and http://host//double/slash",
    r"a & b \\ \hline, then \\\hline and \\frac{a}{b}",
    r"use \\x41 and \\u00e9 here",
    "dir /s /b; sed 's/a/b/g' x; see ./a/b and ../c/d",
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
    "htpasswd -v .htpasswd admin; echo hello | grep h",
    "echo $REGISTRY_TOKEN | docker login -u me --password-stdin registry.example.test",
    "ENABLE_AUTH=true and USE_AUTH=1",
    "The password for admin is required.",
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
                                  "password ", "\\\\a", "a_b_", "Bearer abcdefgh", "C:/x/",
                                  "htpasswd -b ", "-U a%", "Authorization: Basic ",
                                  "the password for a is ", "echo --password-stdin <<< "])
def test_redaction_time_grows_with_the_text_not_its_square(unit):
    text = unit * (60_000 // len(unit))
    start = time.perf_counter()
    outbound(text)
    leaks(text[:2_000])
    # 1.2 MB in 20 lines: only what the quote can show is redacted.
    quote("\n".join([text] * 20), max_chars=40_000)
    # A field whose text redacts to almost nothing widens its window a bounded
    # number of times.
    code(text, limit=200)
    assert time.perf_counter() - start < 2.0, unit


JWT = "eyJ" + "b" * 590
URL = "https://admin:Hunter2pass!@db.internal/api"


def _straddling(head, at, url=URL):
    """`head`, filler, then `url` with its '@' at index `at`, past a window."""
    return head + "k" * (at - url.index("@") - len(head)) + url


@pytest.mark.parametrize("shift", [0, 1, 12])
def test_a_secret_past_a_shrunken_field_window_is_not_shown_in_part(shift):
    # The bearer token redacts to a 20-character marker, so the redacted
    # window falls far short of the room plus a margin.
    head = 'curl -H "Authorization: Bearer ' + JWT + '" '
    assert "Hun" not in code(_straddling(head, 200 + MARGIN + shift), limit=200)
    command = _straddling(head, 160 + MARGIN + shift)
    brief = _brief(_records(progress=[{"type": "cli_tool_call", "call_id": "u", "tool": "Bash",
                                       "arguments": {"command": command}}]))
    assert "Hun" not in brief
    # The window widened, so the rest of the command is still shown.
    assert f"https://{OMITTED}@db.internal/api" in brief


@pytest.mark.parametrize("url", [URL, "postgres://app:Hunter2pass!@db.internal/app"])
def test_a_secret_past_a_shrunken_quote_line_is_not_shown_in_part(url):
    # Each host path becomes a 19-character marker, so the redacted lines leave
    # the last line more room than its raw window holds.
    path = "C:/Users/zain/AppData/Local/Programs/Python/Python312/lib/site-packages/pkg/sub/"
    lines = [f"File {path}connection_pool.py, line {n:03d}, in connect" for n in range(54)]
    room = 8_000 - sum(map(len, lines))
    assert room < 2_000 - MARGIN
    goal = "\n".join(lines + [_straddling(" clone ", room + MARGIN, url)])
    assert "Hun" not in quote(goal)
    assert "Hun" not in _brief(_records(goal=goal))


def test_a_cut_quote_line_keeps_a_margin_of_its_window_unshown():
    line = "x" * 1_990 + " " + "y" * 2_000
    out = quote(line, line_chars=2_000)
    assert out.splitlines()[0] == "> " + line[:2_000]
    shrunk = "password=" + "p" * 1_000 + " " + line
    shown = quote(shrunk, line_chars=2_000).splitlines()[0]
    assert len(shown) - 2 <= len(outbound(shrunk[:2_000 + MARGIN])) - MARGIN
