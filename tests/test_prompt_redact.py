"""prompt_redact: identifiers become stable placeholders before a hosted model reads them.

Identifier strings are built at run time so this file does not itself carry them.
"""
import io
import json

import pytest

from harness import prompt_redact as R

BS = chr(92)
WIN_HOME = "C:" + BS + "Users" + BS + "pat"
POSIX_HOME = "/" + "home" + "/" + "pat"
ADDR = "pat.lee" + "@" + "mail.co"
OTHER = "kim" + "@" + "lab.org"
KEY = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def make(**kw):
    base = dict(home=WIN_HOME, user="pat", hosts={"ORCHID-WS"}, deny=[])
    base.update(kw)
    return R.Redactor(**base)


def test_home_path_in_either_separator_becomes_tilde():
    text, counts = make().redact(f"open {WIN_HOME}{BS}notes.txt and C:/users/PAT/x.py")
    assert text == f"open ~{BS}notes.txt and ~/x.py"
    assert counts == {"home-path": 2}


def test_posix_home_and_other_user_folders():
    r = make(home=POSIX_HOME)
    text, _ = r.redact(f"{POSIX_HOME}/src and /Users/alex/Desktop and D:{BS}Users{BS}sam{BS}a")
    assert text == f"~/src and ~/Desktop and ~{BS}a"


def test_user_and_machine_names_are_whole_words_only():
    text, counts = make().redact("pat ran it on orchid-ws; compatible patterns stay")
    assert text == "USER ran it on HOST; compatible patterns stay"
    assert counts == {"machine-name": 1, "user-name": 1}


def test_emails_numbered_stably_and_safe_addresses_kept():
    text, counts = make().redact(f"{ADDR}, {OTHER}, {ADDR.upper()}, a@example.com, "
                                 "1+x@users.noreply.github.com")
    assert text == ("EMAIL-1, EMAIL-2, EMAIL-1, a@example.com, "
                    "1+x@users.noreply.github.com")
    assert counts == {"email": 3}


def test_deny_list_values_become_ids(tmp_path):
    deny = tmp_path / "deny.txt"
    deny.write_text("# serials\nSN-[0-9]{6}\nlantern\n", encoding="utf-8")
    r = make(deny=R.deny_patterns(str(deny)))
    text, counts = r.redact("disk SN-123456, again SN-123456, then lantern")
    assert text == "disk ID-1, again ID-1, then ID-2"
    assert counts == {"deny-list": 3}


def test_named_deny_list_that_is_missing_is_an_error(tmp_path, monkeypatch):
    with pytest.raises(FileNotFoundError):
        R.deny_patterns(str(tmp_path / "absent.txt"))
    monkeypatch.setenv("FLYWHEEL_REDACT_DENYLIST", str(tmp_path / "absent.txt"))
    with pytest.raises(FileNotFoundError):
        R.deny_patterns()


def test_credentials_use_the_trace_redact_catalog():
    text, counts = make().redact(f"token {KEY} here")
    assert KEY not in text and "[REDACTED:" in text
    assert counts == {"credential": 1}
    text, counts = make(credentials=False).redact(f"token {KEY} here")
    assert KEY in text and counts == {}


def test_clean_text_is_returned_unchanged():
    sample = "Refactor harness/checks/partial.py; keep the receipt schema at v2."
    assert make().redact(sample) == (sample, {})


def test_hook_passes_clean_prompt_and_blocks_with_redacted_copy():
    r = make()
    assert R.hook_response({"prompt": "fix the parser"}, r) is None
    reply = R.hook_response({"prompt": f"read {WIN_HOME}{BS}a.txt and mail {ADDR}"}, r)
    assert reply["decision"] == "block"
    assert reply["reason"].endswith(f"read ~{BS}a.txt and mail EMAIL-1")
    assert ADDR not in reply["reason"] and WIN_HOME not in reply["reason"]


def test_cli_filter_and_hook(monkeypatch):
    real = R.Redactor
    monkeypatch.setattr(R, "Redactor", lambda **kw: real(**{**dict(
        home=WIN_HOME, user="pat", hosts={"ORCHID-WS"}), **kw}))
    out, err = io.StringIO(), io.StringIO()
    assert R.main(["filter", "--no-credentials"], io.StringIO(f"to {ADDR}"), out, err) == 0
    assert out.getvalue() == "to EMAIL-1"
    assert json.loads(err.getvalue()) == {"prompt_redact": {"email": 1}}
    out = io.StringIO()
    event = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "on orchid-ws"})
    assert R.main(["hook"], io.StringIO(event), out, io.StringIO()) == 0
    assert json.loads(out.getvalue())["decision"] == "block"
    out = io.StringIO()
    assert R.main(["hook"], io.StringIO('{"prompt": "plain"}'), out, io.StringIO()) == 0
    assert out.getvalue() == ""
    assert R.main(["hook"], io.StringIO("not json"), io.StringIO(), io.StringIO()) == 2
