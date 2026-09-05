"""test_lane_http.py -- the one lane nobody installs.

bulletin runs on the open web, so it is the first lane the roster cannot check
by looking at the filesystem. These are the falsifiers for what that costs: an
empty argv where every other lane has one, an endpoint that comes from the
environment rather than from this file, and a status vocabulary that has to
distinguish "this workstation is missing something" from "the board is down".
"""
from __future__ import annotations

import harness.lanes as lanes
from harness.lanes import DECLARED, LANES, install_lane, lane_status


def test_the_http_lane_declares_an_endpoint_instead_of_an_argv():
    # bulletin runs on the open web. There is nothing to spawn, so the argv is
    # empty and the roster reads DECLARED rather than MISSING: nothing is
    # missing from this workstation, the board simply lives somewhere else.
    lane = LANES["bulletin"]
    assert lane.kind == "http" and lane.mcp_command() == []
    assert lane_status("bulletin", probe=False)["status"] == DECLARED


def test_the_board_ships_with_an_endpoint_so_a_compiled_app_needs_no_setup(monkeypatch):
    # Until the board was deployed this lane carried no url, so every compiled
    # build read it as unreachable until its user found the environment variable
    # and typed the host. The board is public and needs no key, so the address
    # belongs in the build. The variable still wins for anyone running their own.
    monkeypatch.delenv("FLYWHEEL_BULLETIN_URL", raising=False)
    endpoint = LANES["bulletin"].endpoint()
    assert endpoint.startswith("https://"), "a board reached over the open web is not plaintext"
    assert endpoint.endswith("/mcp"), "the lane speaks MCP, so the compiled default is the MCP path"
    assert endpoint in lane_status("bulletin", probe=False)["detail"]


def test_an_unpointed_http_lane_names_the_variable_that_points_it(monkeypatch):
    # The falsifier for a lane whose deployment nobody has chosen: no compiled
    # default and no variable. The detail has to name the variable that fixes it
    # or the roster reports a dead end with no way out of it.
    monkeypatch.delenv("FLYWHEEL_BULLETIN_URL", raising=False)
    monkeypatch.setattr(LANES["bulletin"], "url", "")
    detail = lane_status("bulletin", probe=False)["detail"]
    assert "no endpoint" in detail and "FLYWHEEL_BULLETIN_URL" in detail


def test_the_environment_points_the_lane_at_a_deployment(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_BULLETIN_URL", "https://board.example/mcp")
    assert LANES["bulletin"].endpoint() == "https://board.example/mcp"
    assert "https://board.example/mcp" in lane_status("bulletin", probe=False)["detail"]
    assert lanes.resolve_mcp_launch("bulletin").url == "https://board.example/mcp"


def test_an_http_lane_that_cannot_be_reached_stays_declared(monkeypatch):
    # A probe against an endpoint nothing answers must report the failure and
    # keep the lane declared. Reporting MISSING would blame the workstation for
    # a board that is simply down.
    monkeypatch.setenv("FLYWHEEL_BULLETIN_URL", "http://127.0.0.1:9/mcp")
    r = lane_status("bulletin", probe=True, timeout=2.0)
    assert r["status"] == DECLARED and "MCP probe failed" in r["detail"]


def test_install_lane_http_is_noop():
    r = install_lane("bulletin")
    assert r["installed"] is True and "http" in r["detail"]


def test_the_installer_never_tries_to_package_manage_the_board():
    from harness.cli_entry import _parse_lane_args  # noqa: F401  (import parity)
    names = [n for n, l in LANES.items() if l.kind not in ("bundled", "http")]
    assert "bulletin" not in names and "local-model" not in names
    assert "gather" in names
