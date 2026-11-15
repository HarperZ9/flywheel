"""Every module that opens a network connection is on a list, with facts the test checks.

Fifth review round of 2.0.0: a route that can reach a provider must not be
added without accounting, so every module under `harness/` that opens a
network connection had to be on a list. The fourth independent review then
showed what that list could not do: it read syntax, 24 of its 32 rows said
"not examined", and seven routes reached a provider unrecorded through a
module that was on the list as accounted.

Since the sixth round the route question is answered by behaviour
(tests/test_gateway_route_reach.py exercises every route over HTTP) and by
the transports themselves (harness/gateway_reach.py refuses a model request
that has no ledger account). This file keeps the module list, and every row
now carries facts that are checked here, none left unexamined:

  kind      what the module's connections are for (below);
  gateway   whether the gateway can load the module at all, checked against
            the import graph of harness/gateway.py with every import
            followed, the ones inside functions included. A module the
            gateway cannot load cannot serve a gateway route;
  the opener: a module that calls `urlopen` directly follows redirects, so it
            must be on BARE with the reason it sends no credential. Every
            other client opens its requests through an opener that follows
            none (tests/test_gateway_no_redirect.py runs them).

What this is and is not. The scans read syntax: calls named `urlopen`,
`build_opener`, `create_connection`, `HTTPConnection`, `HTTPSConnection` and
`open_request`, and import statements. A connection opened another way (a
third-party client, a subprocess, `socket.socket().connect`) and an import
made through `importlib` are not seen.
"""
import ast
from pathlib import Path

import pytest

# Not in the release gate: that gate runs against the built wheel with the source tree's
# `harness/` moved away, and this file reads the source.
ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "harness"
OPENS = {"urlopen", "build_opener", "create_connection", "HTTPConnection", "HTTPSConnection",
         "open_request"}                # http_no_redirect, and endpoints_http.send under that name

ACCOUNT = "model requests; each leaves inside a ledger account, and the transport refuses one that does not"
TRACE = "model requests of a gateway agent run, recorded in the run's own trace"
LOCAL = "a model server on this machine; no provider account, no credential"
META = "asks a provider for a list or checks a key; runs no model"
SERVICE = "a named service that is not a model provider"
PLUMBING = "part of the gateway's own plumbing; no provider"
KINDS = (ACCOUNT, TRACE, LOCAL, META, SERVICE, PLUMBING)

# module -> (kind, what it is, the test that shows it or "", can the gateway load it)
INVENTORY = {
    "endpoints_http.py": (ACCOUNT, "the transport of the model interfaces and the backends; "
                          "token counting is the one unbilled contact",
                          "tests/test_gateway_contact_invariant.py", True),
    "endpoints_connect.py": (PLUMBING, "the connect that endpoints_http's opener uses; reached "
                             "only through it", "tests/test_gateway_loopback_connect.py", True),
    "proposer.py": (ACCOUNT, "the hosted proposers behind every route that names an endpoint; "
                    "ServeProposer is the local model server",
                    "tests/test_gateway_route_accounting.py", True),
    "gateway_embeddings.py": (ACCOUNT, "/v1/embeddings",
                              "tests/test_gateway_chat_route_accounting.py", True),
    "preaction/judge.py": (ACCOUNT, "the optional judge model of the pre-action monitor",
                           "tests/test_gateway_route_accounting.py", True),
    "preaction/judge_typed.py": (ACCOUNT, "the typed mode of that judge",
                                 "tests/test_gateway_route_accounting.py", True),
    "gateway_agent_transport.py": (TRACE, "/api/agent, both tool protocols",
                                   "tests/test_gateway_agent_contact_invariant.py", True),
    "gateway.py": (LOCAL, "the health probe of, and the proxy to, the model server on this "
                   "machine", "tests/test_gateway_route_reach.py", True),
    "local_agent.py": (LOCAL, "the serve and Ollama backends of the local lane", "", True),
    "model_ollama.py": (LOCAL, "an Ollama daemon on this machine", "", False),
    "trace_observation/behavioral/subject.py": (LOCAL, "a model under a behavioral test", "", False),
    "trace_observation/openweight/capture_local.py": (LOCAL, "a local Ollama model", "", False),
    "monitor_gate/monitors.py": (LOCAL, "an Ollama monitor a gate run names", "", False),
    "cross_harness_adapters.py": (LOCAL, "a loopback executor of another harness", "", False),
    "model_roster.py": (META, "lists the models an endpoint serves",
                        "tests/test_gateway_no_redirect.py", True),
    "key_check.py": (META, "one GET to a provider's models list to check a key", "", False),
    "gateway_ledger_relay.py": (PLUMBING, "a worker process sends its ledger entries to its "
                                "gateway over loopback", "tests/test_gateway_route_accounting.py",
                                True),
    "http_no_redirect.py": (PLUMBING, "the opener that follows no redirect",
                            "tests/test_gateway_no_redirect.py", True),
    "capture_hooks/client.py": (PLUMBING, "a hook's call to the local gateway", "", True),
    "egress_proxy.py": (PLUMBING, "the route out of a confined run", "", True),
    "doctor_cli.py": (PLUMBING, "`flywheel doctor` asks the local gateway", "", False),
    "mcp_http.py": (SERVICE, "an MCP server over HTTP that the owner registered",
                    "tests/test_gateway_no_redirect.py", True),
    "web_fetch_pinned.py": (SERVICE, "the pinned web fetch tool", "", True),
    "bulletin_media_http.py": (SERVICE, "Bulletin media reads", "", True),
    "bulletin_signed_transport.py": (SERVICE, "Bulletin signed transport", "", True),
    "bulletin_observer.py": (SERVICE, "Bulletin public records", "", False),
    "anchor_submit.py": (SERVICE, "OpenTimestamps calendars", "", False),
    "arc_agi3.py": (SERVICE, "the ARC Prize agents API", "tests/test_gateway_no_redirect.py",
                    False),
    "datapipe/access.py": (SERVICE, "dataset source access", "", False),
    "enterprise_envs/http_client.py": (SERVICE, "enterprise environment controls", "", False),
    "raw_lane_install.py": (SERVICE, "fetches the raw lane's release binary", "", False),
    "recheck.py": (SERVICE, "recheck manifests", "", False),
    "rekor_submit.py": (SERVICE, "Sigstore's Rekor", "", False),
    "zenodo_deposit.py": (SERVICE, "Zenodo deposits", "", False),
}

# module -> why its direct `urlopen` call, which follows redirects, carries no credential
BARE = {
    "endpoints_http.py": "only when a test replaced `urlopen`; the real path is the no-redirect opener",
    "http_no_redirect.py": "only when a test replaced `urlopen`",
    "proposer.py": "ServeProposer, to the local model server, and a test's replacement",
    "gateway.py": "the local model server: a probe and a proxy that send Content-Type only",
    "local_agent.py": "a model server on this machine; Content-Type only",
    "model_ollama.py": "an Ollama daemon on this machine; no header",
    "monitor_gate/monitors.py": "an Ollama endpoint; Content-Type only",
    "trace_observation/behavioral/subject.py": "a local server; Content-Type only",
    "trace_observation/openweight/capture_local.py": "a local server; Content-Type only",
    "doctor_cli.py": "a loopback URL; no header",
    "anchor_submit.py": "public calendars; no credential",
    "datapipe/access.py": "public datasets; a User-Agent only",
    "enterprise_envs/http_client.py": "headers come from the caller; no caller passes a credential",
    "raw_lane_install.py": "a public release download; no credential",
    "recheck.py": "manifest URLs; no credential",
    "rekor_submit.py": "a public transparency log; no credential",
}


def _calls(source: str) -> set:
    out = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            out.add(node.func.attr if isinstance(node.func, ast.Attribute) else getattr(
                node.func, "id", ""))
    return out


def opens_a_connection(source: str) -> bool:
    """Does this source call one of the names in OPENS?"""
    return bool(_calls(source) & OPENS)


def _modules() -> dict:
    return {path.relative_to(HARNESS).as_posix(): path.read_text(encoding="utf-8")
            for path in HARNESS.rglob("*.py") if "_vendor" not in path.parts}


def found() -> set:
    return {name for name, source in _modules().items() if opens_a_connection(source)}


def imports(name: str, source: str) -> set:
    """The harness modules this source imports, at the top or inside a function."""
    package, out = name.split("/")[:-1], set()
    for node in ast.walk(ast.parse(source)):
        wanted = []
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:len(package) - (node.level - 1)]
                module = base + (node.module.split(".") if node.module else [])
            elif node.module and node.module.split(".")[0] == "harness":
                module = node.module.split(".")[1:]
            else:
                continue
            wanted = [module] + [module + [alias.name] for alias in node.names]
        elif isinstance(node, ast.Import):
            wanted = [alias.name.split(".")[1:] for alias in node.names
                      if alias.name.startswith("harness.")]
        for parts in filter(None, wanted):
            for candidate in ("/".join(parts) + ".py", "/".join(parts) + "/__init__.py"):
                if (HARNESS / candidate).is_file():
                    out.add(candidate)
    return out


def loaded_by_the_gateway() -> set:
    modules, seen, todo = _modules(), set(), ["gateway.py"]
    while todo:
        name = todo.pop()
        if name not in seen and name in modules:
            seen.add(name)
            todo.extend(imports(name, modules[name]))
    return seen


def test_every_module_that_opens_a_network_connection_is_on_the_list():
    unlisted = sorted(found() - set(INVENTORY))
    assert not unlisted, (
        f"{unlisted} open a network connection and are not in INVENTORY. Add each with its "
        "kind, whether the gateway can load it, and the test that shows it.")
    stale = sorted(set(INVENTORY) - found())
    assert not stale, f"{stale} are in INVENTORY and no longer open a network connection"


def test_no_row_is_left_unexamined_and_each_accounted_row_names_a_test_that_exists():
    for module, (kind, why, test, _gateway) in INVENTORY.items():
        assert kind in KINDS and why, module
        if kind in (ACCOUNT, TRACE):
            assert test, f"{module}: no test is named for it"
        assert not test or (ROOT / test).is_file(), f"{module}: {test} does not exist"


def test_whether_the_gateway_can_load_a_module_is_what_the_list_says():
    """A module marked as outside the gateway that the gateway comes to import fails here,
    and has to be looked at again: it may now serve a gateway route."""
    loaded = loaded_by_the_gateway()
    assert len(loaded) > 500            # the walk really follows the gateway's imports
    wrong = {module: row[3] for module, row in INVENTORY.items() if (module in loaded) != row[3]}
    assert not wrong, f"the gateway's import graph disagrees with INVENTORY for {wrong}"


def test_a_module_that_sends_model_requests_from_the_gateway_is_accounted_or_local():
    """Inside the gateway, a model request is accounted (ledger or trace) or goes to the
    model server on this machine. An accounted module names the reach rule or the checked
    transport in its source."""
    modules = _modules()
    for module, (kind, _why, _test, gateway) in INVENTORY.items():
        if kind == ACCOUNT:
            assert any(mark in modules[module] for mark in (
                "gateway_reach", "endpoints_http import send", "from .endpoints_http import")), (
                f"{module} is marked accounted and does not go through the checked transport")
        if kind == TRACE:
            assert gateway and "NoRedirect" in modules[module]


def test_a_direct_urlopen_is_only_where_no_credential_is_sent():
    """`urllib.request.urlopen` follows a redirect and re-sends the request's headers."""
    direct = {name for name, source in _modules().items() if "urlopen" in _calls(source)}
    unlisted = sorted(direct - set(BARE))
    assert not unlisted, (
        f"{unlisted} call `urlopen` directly, which follows redirects. Open the request with "
        "harness.http_no_redirect.open_request, or add the module to BARE with the reason it "
        "sends no credential.")
    assert not sorted(set(BARE) - direct), "BARE lists a module that no longer calls urlopen"


@pytest.mark.parametrize("source, opens", [
    ("import urllib.request\nurllib.request.urlopen('http://127.0.0.1:9')\n", True),
    ("from urllib.request import urlopen\nurlopen('http://127.0.0.1:9')\n", True),
    ("import http.client\nhttp.client.HTTPSConnection('example.invalid')\n", True),
    ("import socket\nsocket.create_connection(('127.0.0.1', 9))\n", True),
    ("from .http_no_redirect import open_request\nopen_request(None, 1)\n", True),
    ("def urlopen_later():\n    return 'urlopen is only a word here'\n", False),
])
def test_control_the_scan_sees_a_connection_and_nothing_else(source, opens):
    assert opens_a_connection(source) is opens


def test_control_the_import_walk_follows_an_import_inside_a_function():
    source = "def late():\n    from .gateway_reach import check\n    from . import proposer\n"
    assert imports("endpoints_http.py", source) == {"gateway_reach.py", "proposer.py"}
    assert imports("preaction/judge.py", "from ..endpoints_http import send\n") == {
        "endpoints_http.py"}
