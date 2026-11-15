"""Role-boundary tests for the Canon and Relay interop manifests.

These tests are deliberately about declared contracts, not live probes. Plexus
matches manifest strings and cited modules; it does not import Canon or Relay.
"""
from __future__ import annotations

from pathlib import PurePosixPath

from plexus.mesh import discover
from plexus.plan import route
from plexus.registry import builtin_manifests


def _manifests():
    return {manifest.organ: manifest for manifest in builtin_manifests()}


def _caps(ports):
    return {port.capability for port in ports}


def _edge(mesh, producer, consumer, capability):
    return any(
        edge.producer == producer
        and edge.consumer == consumer
        and edge.capability == capability
        for edge in mesh.edges
    )


def test_canon_declares_shipped_context_artifacts_without_capture_claims():
    canon = _manifests()["canon"]
    emits = _caps(canon.emits)
    consumes = _caps(canon.consumes)

    assert {"canon.record/v1", "canon.capsule/v1", "canon.readiness-probe/1"} <= emits
    assert {"canon.record/v1", "canon.atom/v1", "canon.readiness-response/1"} <= consumes
    assert "canon.context-capture/1" not in emits
    assert "canon.shared-preflight/1" not in emits


def test_relay_declares_shipped_connectivity_and_execution_artifacts_only():
    relay = _manifests()["relay"]
    emits = _caps(relay.emits)
    consumes = _caps(relay.consumes)

    assert {"relay.agent-run-result/1", "relay.session-ledger/1", "relay.rvc/v1"} <= emits
    assert {"relay.mcp-run-request/v1", "relay.rvc/v1", "relay.session-ledger/1"} <= consumes
    assert "plexus.route-plan/1" not in consumes
    assert "canon.capsule/v1" not in consumes


def test_canon_and_relay_form_only_edges_their_sources_actually_support():
    mesh = discover(builtin_manifests())

    assert _edge(mesh, "canon", "canon", "canon.record/v1")
    assert _edge(mesh, "canon", "canon", "canon.capsule/v1")
    assert _edge(mesh, "relay", "relay", "relay.session-ledger/1")
    assert _edge(mesh, "relay", "relay", "relay.rvc/v1")

    assert route(mesh, "canon", "relay")["connected"] is False
    assert route(mesh, "relay", "canon")["connected"] is False


def test_canon_and_relay_evidence_paths_are_repo_relative_public_paths():
    for organ in ("canon", "relay"):
        manifest = _manifests()[organ]
        for path in manifest.evidence:
            parsed = PurePosixPath(path)
            assert not parsed.is_absolute()
            assert "\\" not in path
            assert ":" not in path
            assert not path.startswith(("private/", "protected/", "secrets/"))
