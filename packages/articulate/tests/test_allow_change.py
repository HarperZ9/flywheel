"""allow_change: named protected change kinds an edit may make, always reported."""
import base64
import json

import pytest

from articulate import edit_options, host_edit, local_mcp
from articulate.meaning_guard import guard_rewrite

TEXT = "We measured 14 samples on site.\n\nSee https://example.org/a for the data."
NUMBER_EDIT = "We measured 15 samples on site.\n\nSee https://example.org/a for the data."


def test_allowed_number_change_is_accepted_and_reported():
    out = guard_rewrite(TEXT, NUMBER_EDIT, allow={"number"})
    assert out["text"] == NUMBER_EDIT
    assert out["refused"] == []
    assert out["allowed_changes"] == [{"paragraph": 0, "kind": "number"}]


def test_number_change_without_allow_is_retained():
    out = guard_rewrite(TEXT, NUMBER_EDIT)
    assert out["text"] == TEXT
    assert out["refused"][0]["reasons"] == ["number protected spans changed"]
    assert "allowed_changes" not in out


def test_allowing_one_kind_does_not_allow_another():
    rewrite = "We measured 15 samples on site.\n\nSee https://example.org/b for the data."
    out = guard_rewrite(TEXT, rewrite, allow={"number"})
    assert out["text"] == NUMBER_EDIT
    assert out["refused"] == [{"paragraph": 1, "reasons": ["url protected spans changed"]}]
    assert out["allowed_changes"] == [{"paragraph": 0, "kind": "number"}]


def test_claim_feature_kind_can_be_allowed():
    old, new = "The fix must ship today.", "The fix may ship today."
    assert guard_rewrite(old, new)["text"] == old
    out = guard_rewrite(old, new, allow={"modal"})
    assert out["text"] == new and out["allowed_changes"] == [{"paragraph": 0, "kind": "modal"}]


def test_cross_paragraph_recheck_ignores_only_allowed_kinds():
    # The quote spans the paragraph break, so only the whole-document recheck sees it.
    old = 'We had 14 votes. She said "alpha\n\nbeta" at the end.'
    new = 'We had 15 votes. She said "alpha\n\ngamma" at the end.'
    out = guard_rewrite(old, new, allow={"number"})
    assert out["text"] == old
    assert out["refused"][-1]["reasons"] == ["cross-paragraph protected spans changed"]


@pytest.mark.parametrize("kind", ["disclosure", "added-first-person", "html", "math"])
def test_never_allowable_kinds_raise_naming_the_allowable_list(kind):
    with pytest.raises(ValueError) as err:
        edit_options.parse_allow([kind])
    assert "can never be allowed" in str(err.value)
    assert ", ".join(edit_options.ALLOWABLE) in str(err.value)


def test_unknown_kind_raises_and_mask_reasons_are_not_kinds():
    for name in ("mask", "paragraph alignment changed", "numbers"):
        with pytest.raises(ValueError, match="allowable kinds"):
            edit_options.parse_allow(name)


def test_disclosure_change_stays_refused_whatever_is_allowed():
    old = "Drafted with Claude.\n\nWe had 14 votes."
    new = "Drafted with care.\n\nWe had 15 votes."
    out = guard_rewrite(old, new, allow=set(edit_options.ALLOWABLE))
    assert out["text"] == "Drafted with Claude.\n\nWe had 15 votes."
    assert "disclosure protected spans changed" in out["refused"][0]["reasons"]


def test_plan_without_options_stays_v2_and_with_options_is_v3():
    plain = host_edit.plan_settings(TEXT, host_edit.edit_plan(TEXT)["plan_id"])
    assert plain["schema"] == host_edit.PLAN_V2 and "allow_change" not in plain
    bound = host_edit.plan_settings(
        TEXT, host_edit.edit_plan(TEXT, allow_change="url,number,number")["plan_id"])
    assert bound["schema"] == host_edit.PLAN_V3
    assert bound["allow_change"] == ["number", "url"] and bound["freeze_terms"] == []


def test_submit_reads_the_allowed_set_from_the_plan():
    plan = host_edit.edit_plan(TEXT, allow_change=["number"])
    out = host_edit.edit_submit(TEXT, NUMBER_EDIT, plan["plan_id"])
    assert out["text"] == NUMBER_EDIT
    assert out["allowed_changes"] == out["receipt"]["allowed_changes"] == [
        {"paragraph": 0, "kind": "number"}]
    plain = host_edit.edit_submit(TEXT, NUMBER_EDIT, host_edit.edit_plan(TEXT)["plan_id"])
    assert plain["text"] == TEXT and "allowed_changes" not in plain


def _forge(settings):
    return host_edit._token(TEXT, settings)


def test_hand_built_plan_cannot_carry_a_never_allowable_kind():
    settings = host_edit.plan_settings(TEXT, host_edit.edit_plan(TEXT, allow_change=["number"])["plan_id"])
    settings["allow_change"] = ["disclosure", "number"]
    with pytest.raises(ValueError):
        host_edit.plan_settings(TEXT, _forge(settings))
    with pytest.raises(ValueError):
        host_edit.edit_submit(TEXT, NUMBER_EDIT, _forge(settings))


def test_v1_plan_still_verifies():
    settings = host_edit._settings(None, None, "fix", False, False)
    settings = {k: v for k, v in settings.items() if k in host_edit._PLAN_KEYS[host_edit.PLAN_V1]}
    settings["schema"] = host_edit.PLAN_V1
    assert host_edit.plan_settings(TEXT, _forge(settings))["schema"] == host_edit.PLAN_V1


def test_freeze_terms_protect_a_term():
    old, new = "Articulate reads the draft.", "The tool reads the draft."
    plan = host_edit.edit_plan(old, freeze_terms=["Articulate"])
    assert any(s["kind"] == "term" for s in plan["protected_spans"])
    out = host_edit.edit_submit(old, new, plan["plan_id"])
    assert out["text"] == old
    assert out["refused"][0]["reasons"] == ["term protected spans changed"]


def test_deterministic_edit_threads_the_option():
    text = "We measured 14 samples — a lot."
    out = host_edit.deterministic_edit(text, allow_change=["number"])
    assert out["text"] == "We measured 14 samples, a lot." and out["allowed_changes"] == []


def _call(name, args):
    resp = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": args}})
    result = resp["result"]
    return result.get("isError", False), json.loads(result["content"][0]["text"]) \
        if not result.get("isError") else result["content"][0]["text"]


def test_stdio_mcp_tools_take_allow_change():
    schemas = {t["name"]: t["inputSchema"]["properties"] for t in local_mcp.TOOLS}
    for name in ("fix", "polish", "edit_plan"):
        assert schemas[name]["allow_change"]["items"]["enum"] == list(edit_options.ALLOWABLE)
    err, plan = _call("edit_plan", {"text": TEXT, "allow_change": ["number"]})
    assert not err
    encoded = plan["plan_id"].rsplit(".", 1)[0]
    settings = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert settings["allow_change"] == ["number"]
    err, fixed = _call("fix", {"text": TEXT, "backend": "none", "allow_change": ["number"]})
    assert not err and fixed["allowed_changes"] == []
    err, message = _call("fix", {"text": TEXT, "backend": "none", "allow_change": ["disclosure"]})
    assert err and "can never be allowed" in message


_FASTMCP_PROPS = """
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
import fastmcp
from articulate import mcp_server

async def main():
    async with fastmcp.Client(mcp_server.build_server()) as client:
        tools = await client.list_tools()
    print(json.dumps({t.name: sorted(t.inputSchema.get("properties", {})) for t in tools}))

asyncio.run(main())
"""


def fastmcp_properties():
    """Input property names per tool on the FastMCP server, from a child process
    so fastmcp never enters this test process's modules."""
    import importlib.util
    import pathlib
    import subprocess
    import sys
    if importlib.util.find_spec("fastmcp") is None:
        pytest.skip("fastmcp is not installed (the [mcp] extra)")
    src = str(pathlib.Path(local_mcp.__file__).resolve().parents[1])
    run = subprocess.run([sys.executable, "-c", _FASTMCP_PROPS, src],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_fastmcp_tools_take_allow_change():
    props = fastmcp_properties()
    for name in ("fix", "polish", "edit_plan"):
        assert "allow_change" in props[name], name
    assert "allow_change" not in props["judge"]


def test_cli_allow_change_binds_the_plan_and_rejects_never_kinds(tmp_path, capsys):
    from articulate import cli
    src = tmp_path / "a.md"
    src.write_text(TEXT, encoding="utf-8")
    assert cli.main(["plan", str(src), "--allow-change", "number"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert host_edit.plan_settings(TEXT, plan["plan_id"])["allow_change"] == ["number"]
    assert cli.main(["fix", str(src), "--backend", "none", "--allow-change", "html"]) == 2
    assert "can never be allowed" in capsys.readouterr().err
