"""Shared test setup.

The MCP server confines every run's root to the root it was launched with. Most
tests root their runs in ``tmp_path``, so the launch root is pinned to pytest's
temp base here, the way an operator would launch a server over a workspace.
Tests that exercise the boundary itself set their own launch root.
"""
import pytest


@pytest.fixture(autouse=True)
def _mcp_launch_root(monkeypatch, tmp_path_factory):
    import relay.local_mcp as m
    from relay.mcp_grants import StartGrants

    monkeypatch.setattr(m, "_GRANTS", StartGrants(root=str(tmp_path_factory.getbasetemp())))


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A server folder with a planted project hook, and CLI stand-ins' bin folder."""
    from cli_stand_in import make_world
    return make_world(tmp_path, monkeypatch)
