"""The stdio MCP server must work from a bare install.

articulate's original MCP surface is built on fastmcp, which is declared under
the ``mcp`` extra. A plain ``pip install articulate-writing`` therefore produced
a package whose MCP entry point raised ``ModuleNotFoundError: No module named
'fastmcp'`` when a host launched it. The install reported success and the server
never started.

These tests pin the replacement: the tool surface is served with nothing but the
standard library, it answers the same five tools, and it cannot quietly drift
away from the fastmcp surface it mirrors.
"""
import ast
import importlib.util
import io
import json
import os
import pathlib
import sys
import subprocess

import pytest

from articulate import __version__, local_mcp

_SRC = pathlib.Path(local_mcp.__file__).parent


def _request(method, params=None, rid=1):
    req = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        req["params"] = params
    return local_mcp.handle(req)


def _call(name, arguments=None):
    response = _request("tools/call", {"name": name, "arguments": arguments or {}})
    return response["result"]


def _payload(result):
    return json.loads(result["content"][0]["text"])


def test_the_server_imports_without_fastmcp():
    """Import with installed packages disabled, independent of test order."""
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import articulate.local_mcp; "
        "assert 'fastmcp' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code, str(_SRC.parent)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        "the local MCP server must import with only the standard library: "
        + result.stderr
    )


def test_initialize_reports_identity_and_protocol():
    result = _request("initialize")["result"]
    assert result["protocolVersion"] == local_mcp.PROTOCOL
    assert result["serverInfo"] == {"name": "articulate", "version": __version__}
    assert "tools" in result["capabilities"]


def test_tools_list_matches_the_fastmcp_surface():
    """A drift guard that does not need fastmcp installed.

    The fastmcp server declares its tools as functions decorated with
    ``@mcp.tool`` inside ``build_server``. Parsing that file for those names is
    cheaper than importing it, and it works in CI where the extra is absent.
    """
    tree = ast.parse((_SRC / "mcp_server.py").read_text(encoding="utf-8"))
    decorated = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                decorated.add(node.name)
    assert decorated, "found no @mcp.tool functions; the parse assumption broke"
    served = {tool["name"] for tool in local_mcp.TOOLS}
    assert decorated <= served, (
        "the fastmcp server exposes tools the stdio server does not: "
        f"{sorted(decorated - served)}")


def test_every_tool_declares_an_object_input_schema():
    for tool in local_mcp.TOOLS:
        assert tool["name"], "a tool with no name"
        assert tool["description"].strip(), f"{tool['name']} has no description"
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        for required in schema.get("required", []):
            assert required in schema["properties"], (
                f"{tool['name']} requires {required!r} but does not declare it")


def test_status_and_doctor_answer_without_a_backend():
    status = _payload(_call("articulate.status"))
    assert status == {"ok": True, "server": "articulate", "version": __version__,
                      "protocol": local_mcp.PROTOCOL}
    doctor = _payload(_call("articulate.doctor"))
    assert doctor["tools"] == [t["name"] for t in local_mcp.TOOLS]
    # The split is the honest part: a host with no LLM backend still gets a
    # working detector, and doctor says which tools that covers.
    assert doctor["local_only"] == ["check", "score", "edit_plan", "edit_submit",
                                    "corpus_check", "title_workshop", "interview",
                                    "restructure_plan", "voice_compare", "voice_apply_plan",
                                    "house_brief", "house_transform", "dialogue_check"]
    assert doctor["needs_llm_backend"] == []
    assert set(doctor["optional_llm_backend"]) == {"judge", "fix", "polish"}
    assert doctor["sampling_advertised"] is False
    assert doctor["editor_default"] == "host"


def test_check_runs_local_and_reports_findings():
    result = _payload(_call("check", {"text": "It is important to note that this "
                                              "leverages a robust solution."}))
    assert isinstance(result, dict)
    assert result, "check returned an empty result"


def test_score_runs_local():
    result = _payload(_call("score", {"text": "The cat sat. Then it left."}))
    assert isinstance(result, dict)
    assert result


@pytest.mark.parametrize("name", ["check", "score"])
def test_a_missing_text_argument_is_a_tool_error_not_a_crash(name):
    result = _call(name, {})
    assert result["isError"] is True
    assert "text" in result["content"][0]["text"]


def test_an_unknown_tool_is_a_tool_error():
    result = _call("articulate.nope")
    assert result["isError"] is True
    assert "unknown tool" in result["content"][0]["text"]


def test_non_object_arguments_are_rejected():
    result = local_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "check", "arguments": "oops"}})["result"]
    assert result["isError"] is True


@pytest.mark.parametrize("req,code", [
    ({"jsonrpc": "1.0", "id": 1, "method": "initialize"}, -32600),
    ({"jsonrpc": "2.0", "id": 1}, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": 5}, -32600),
    ({"jsonrpc": "2.0", "id": {"bad": 1}, "method": "initialize"}, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": "nope"}, -32601),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": []}, -32602),
])
def test_malformed_requests_get_a_typed_error(req, code):
    assert local_mcp.handle(req)["error"]["code"] == code


def test_a_non_dict_request_is_an_invalid_request():
    assert local_mcp.handle(["not", "a", "request"])["error"]["code"] == -32600


def test_a_notification_gets_no_response():
    # No "id" means a notification. Answering one would corrupt the stream.
    assert local_mcp.handle({"jsonrpc": "2.0", "method": "initialize"}) is None


def test_handle_request_is_the_same_dispatcher():
    assert local_mcp.handle_request is local_mcp.handle


def test_serve_round_trips_over_stdio_and_survives_a_bad_line():
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        "not json at all",
        "",
        json.dumps({"jsonrpc": "2.0", "method": "initialize"}),   # notification
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    out = io.StringIO()
    assert local_mcp.serve(io.StringIO("\n".join(lines) + "\n"), out) == 0
    responses = [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]
    # initialize, the parse error, and tools/list. The blank line and the
    # notification produce nothing, and one bad line does not kill the loop.
    assert [r.get("id") for r in responses] == [1, None, 2]
    assert responses[1]["error"]["code"] == -32700
    assert len(responses[2]["result"]["tools"]) == len(local_mcp.TOOLS)


@pytest.mark.skipif(importlib.util.find_spec('fastmcp') is None,
                    reason='optional FastMCP extra is not installed')
def test_optional_fastmcp_negotiated_sampling_and_host_fallback():
    # Keep optional SDK imports outside this process, preserving the bare-import
    # guarantee tested above. This exercises a real in-memory SDK connection.
    script = '''
import asyncio
import os
import subprocess
import urllib.request
from fastmcp import Client
from mcp.types import CreateMessageResult, TextContent
from articulate.mcp_server import build_server
os.environ.pop('ARTICULATE_BACKEND', None)
os.environ.pop('ARTICULATE_LOCAL_ONLY', None)
def forbidden(*args, **kwargs):
    raise AssertionError('unexpected separate model boundary')
subprocess.run = forbidden
urllib.request.urlopen = forbidden
async def sample(messages, params, context):
    return CreateMessageResult(role='assistant',
        content=TextContent(type='text', text='We wait. Today.'), model='scripted-fastmcp')
async def main():
    async with Client(build_server()) as client:
        result = await client.call_tool('fix', {'text': 'We wait.'})
        assert result.data['backend'] == 'host'
        assert result.data['plan_id']
    async with Client(build_server(), sampling_handler=sample) as client:
        result = await client.call_tool('fix', {'text': 'We wait.'})
        assert result.data['backend'] == 'sampling'
        assert result.data['model'] == 'scripted-fastmcp'
        assert result.data['text'] == 'We wait. Today.'
asyncio.run(main())
'''
    env = os.environ.copy()
    env['PYTHONPATH'] = str(_SRC.parent.resolve()) + (
        os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    result = subprocess.run([sys.executable, '-c', script], capture_output=True,
                            text=True, timeout=30, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
