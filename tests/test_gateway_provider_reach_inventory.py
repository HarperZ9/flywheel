"""Every place the harness opens a network connection is on a list, with how it is accounted.

Fifth review round of 2.0.0, the lead's ruling 5: a route that can reach a
provider must not be added without accounting. The tests that watch the
transports (tests/test_gateway_contact_invariant.py and its siblings) cover
the routes that exist. This file covers the ones that do not exist yet: it
reads the source of `harness/` and fails when a module opens a network
connection and is not on the list below, or is on the list and no longer
opens one. Whoever adds such a module has to write down, here, which record a
provider call made there leaves, and name the test that shows it.

What this is and is not. It is a list a person keeps, checked against the
source by syntax: calls named `urlopen`, `build_opener`, `create_connection`,
`HTTPConnection` or `HTTPSConnection`. A connection opened another way (a
third-party client, a subprocess, `socket.socket().connect`) is not seen. The
rows marked "not examined" were read for their purpose only, in round 5; no
claim is made about the record they leave.
"""
import ast
from pathlib import Path

import pytest

# Not in the release gate: that gate runs against the built wheel with the source tree's
# `harness/` moved away, and this file reads the source.
ROOT = Path(__file__).resolve().parents[1]
OPENS = {"urlopen", "build_opener", "create_connection", "HTTPConnection", "HTTPSConnection",
         "open_request"}                # http_no_redirect, and endpoints_http.send under that name

ACCOUNT = "gateway route, recorded through gateway_account (a started entry, then an end entry)"
TRACE = "gateway route, recorded in the agent run's own trace (a started record, then a closing one)"
NO_INFERENCE = "gateway route that runs no model at a provider"
OTHER = "not a gateway provider route; not examined for the record it leaves"

# module -> (how a provider call made there is accounted, why, the test that shows it or "")
INVENTORY = {
    "endpoints_http.py": (ACCOUNT, "the transport of /v1/messages and /v1/responses; token "
                          "counting is the one unbilled contact",
                          "tests/test_gateway_contact_invariant.py"),
    "endpoints_connect.py": (ACCOUNT, "the connect that endpoints_http uses",
                             "tests/test_gateway_loopback_connect.py"),
    "proposer.py": (ACCOUNT, "the proposers behind /v1/chat/completions and /api/route, wrapped "
                    "by LedgeredProposer", "tests/test_gateway_chat_route_accounting.py"),
    "gateway_embeddings.py": (ACCOUNT, "/v1/embeddings",
                              "tests/test_gateway_chat_route_accounting.py"),
    "gateway_agent_transport.py": (TRACE, "/api/agent, both tool protocols",
                                   "tests/test_gateway_agent_contact_invariant.py"),
    "gateway_ledger_relay.py": (NO_INFERENCE, "a child process sends its ledger entries to the "
                                "gateway over loopback; no provider", ""),
    "http_no_redirect.py": (OTHER, "the opener for clients that send a credential", ""),
    "gateway.py": (NO_INFERENCE, "the health probe of, and the proxy to, the model server on "
                   "this machine", ""),
    "model_roster.py": (NO_INFERENCE, "lists the models an endpoint serves", ""),
    "key_check.py": (NO_INFERENCE, "one GET to a provider's models list to check a key", ""),
    "anchor_submit.py": (OTHER, "OpenTimestamps calendars", ""),
    "arc_agi3.py": (OTHER, "the ARC Prize agents API", ""),
    "bulletin_media_http.py": (OTHER, "Bulletin media reads", ""),
    "bulletin_observer.py": (OTHER, "Bulletin public records", ""),
    "bulletin_signed_transport.py": (OTHER, "Bulletin signed transport", ""),
    "capture_hooks/client.py": (OTHER, "a hook's call to the local gateway", ""),
    "cross_harness_adapters.py": (OTHER, "the cross-harness executor's boundaries", ""),
    "datapipe/access.py": (OTHER, "dataset source access", ""),
    "doctor_cli.py": (OTHER, "`flywheel doctor`", ""),
    "egress_proxy.py": (OTHER, "the route out of a confined run", ""),
    "enterprise_envs/http_client.py": (OTHER, "enterprise environment controls", ""),
    "local_agent.py": (OTHER, "models on this machine, for the coding session", ""),
    "mcp_http.py": (OTHER, "MCP over HTTP", ""),
    "model_ollama.py": (OTHER, "an Ollama daemon on this machine", ""),
    "monitor_gate/monitors.py": (OTHER, "monitors a gate run calls", ""),
    "preaction/judge.py": (OTHER, "an optional judge model the owner configures", ""),
    "preaction/judge_typed.py": (OTHER, "the typed mode of that judge", ""),
    "raw_lane_install.py": (OTHER, "fetches the raw lane's release binary", ""),
    "recheck.py": (OTHER, "recheck manifests", ""),
    "rekor_submit.py": (OTHER, "Sigstore's Rekor", ""),
    "trace_observation/behavioral/subject.py": (OTHER, "a model under a behavioral test", ""),
    "trace_observation/openweight/capture_local.py": (OTHER, "a local Ollama model", ""),
    "web_fetch_pinned.py": (OTHER, "the pinned web fetch", ""),
    "zenodo_deposit.py": (OTHER, "Zenodo deposits", ""),
}


def opens_a_connection(source: str) -> bool:
    """Does this source call one of the names in OPENS?"""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(
                node.func, "id", "")
            if name in OPENS:
                return True
    return False


def found() -> set:
    harness = ROOT / "harness"
    return {path.relative_to(harness).as_posix() for path in harness.rglob("*.py")
            if "_vendor" not in path.parts and opens_a_connection(path.read_text(encoding="utf-8"))}


def test_every_module_that_opens_a_network_connection_is_on_the_list():
    unlisted = sorted(found() - set(INVENTORY))
    assert not unlisted, (
        f"{unlisted} open a network connection and are not in INVENTORY. Add each with the "
        "record a provider call made there leaves, and the test that shows it.")
    stale = sorted(set(INVENTORY) - found())
    assert not stale, f"{stale} are in INVENTORY and no longer open a network connection"


def test_each_accounted_row_names_a_test_that_exists():
    for module, (how, _why, test) in INVENTORY.items():
        if how in (ACCOUNT, TRACE):
            assert test and (ROOT / test).is_file(), f"{module}: no test is named for it"
        assert how in (ACCOUNT, TRACE, NO_INFERENCE, OTHER)


@pytest.mark.parametrize("source, opens", [
    ("import urllib.request\nurllib.request.urlopen('http://127.0.0.1:9')\n", True),
    ("from urllib.request import urlopen\nurlopen('http://127.0.0.1:9')\n", True),
    ("import http.client\nhttp.client.HTTPSConnection('example.invalid')\n", True),
    ("import socket\nsocket.create_connection(('127.0.0.1', 9))\n", True),
    ("def urlopen_later():\n    return 'urlopen is only a word here'\n", False),
])
def test_control_the_scan_sees_a_connection_and_nothing_else(source, opens):
    assert opens_a_connection(source) is opens
