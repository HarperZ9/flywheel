"""I10: rules match decoded string values, JSON nested in strings included.

A transcript line is JSON. A secret inside it can sit behind escapes (`\\n`
in a PEM block, `\\u0067` for a letter), inside a string that is itself JSON,
or at the end of a tool output that Flywheel cut at 4000 characters. Each of
those must still be found, and a line that does not parse is scanned both raw
and unescaped, with the redaction applied to the raw bytes.
"""
import json

from harness import trace_redact
from trace_redact_fakes import credential_fakes

KEY = b"planted-fake-redaction-key-000000"
FAKES = credential_fakes()


def _line(value) -> str:
    return json.dumps(value)


def test_pem_block_inside_a_json_string_with_escaped_newlines():
    line = _line({"type": "tool_result", "content": "key:\n" + FAKES["pem_private_key"]})
    assert "\\n" in line and "BEGIN RSA" in line
    out, counts = trace_redact.redact_line(line, key=KEY)
    assert counts == {"pem_private_key": 1}
    decoded = json.loads(out)
    assert "PRIVATE KEY" not in decoded["content"] and decoded["type"] == "tool_result"


def test_double_encoded_assignment_in_a_nested_json_string():
    secret = "correcthorse-battery"
    inner = json.dumps({"api_key": secret, "model": "m"})
    line = _line({"message": {"content": inner}})
    out, counts = trace_redact.redact_line(line, key=KEY)
    assert counts == {"credential_assignment": 1}
    assert secret not in out
    nested = json.loads(json.loads(out)["message"]["content"])
    assert nested["model"] == "m" and nested["api_key"].startswith("[REDACTED:")


def test_unicode_escaped_token_is_found_after_decoding():
    token = FAKES["github_token"]
    line = '{"text": "' + "\\u0067" + token[1:] + '"}'
    assert token not in line
    out, counts = trace_redact.redact_line(line, key=KEY)
    assert counts == {"github_token": 1}
    assert token not in json.loads(out)["text"]


def test_token_cut_at_the_end_of_a_capped_string_is_redacted():
    cut = ("x" * 3989) + " " + "gh" + "p_" + "abcd12"
    assert len(cut) == 4000
    out, counts = trace_redact.redact_line(_line({"output": cut}), key=KEY)
    assert counts == {"github_token": 1}
    assert json.loads(out)["output"].endswith("]") and "abcd12" not in out


def test_the_same_short_prefix_mid_string_is_not_a_token():
    text = "the ghp_x branch name is short"
    assert trace_redact.redact_line(_line({"t": text}), key=KEY)[1] == {}


def test_unparseable_line_is_scanned_raw_and_unescaped_and_bytes_outside_stay():
    token = FAKES["github_token"]
    line = '{"broken": "' + "\\u0067" + token[1:] + '" trailing-garbage'
    out, counts = trace_redact.redact_line(line, key=KEY)
    assert counts == {"github_token": 1}
    assert out.startswith('{"broken": "[REDACTED:github_token:')
    assert out.endswith('" trailing-garbage')


def test_a_line_with_no_hit_is_returned_byte_for_byte():
    line = '{"a":  1, "b": "plain text", "c": [1,2 ,3]}'
    assert trace_redact.redact_line(line, key=KEY) == (line, {})


def test_credential_named_keys_redact_their_values_at_any_depth_up_to_four():
    value = {"k": json.dumps({"k2": json.dumps({"k3": json.dumps(
        {"password": "hunter2hunter2"})})})}
    out, counts = trace_redact.redact_line(_line(value), key=KEY)
    assert counts == {"credential_assignment": 1} and "hunter2hunter2" not in out


def test_redacted_keys_with_short_or_non_string_values_are_kept():
    line = _line({"password": "", "token_count": 42, "api_key": None})
    assert trace_redact.redact_line(line, key=KEY) == (line, {})
