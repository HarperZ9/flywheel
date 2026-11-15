"""Contract falsifiers for the bidirectional Mneme/Crucible replay loop."""
from pathlib import Path

import pytest

from plexus.mesh import discover
from plexus.plan import route
from plexus.registry import builtin_manifests, load_dir


REPLAY_TEMPLATE = "crucible.replay-template/1"
REPLAY_PACK = "crucible.replay-pack/1"
STALE_REPLAY_PACK_ALIAS = "crucible.recheck-pack/1"


def _manifest_sets():
    shipped = Path(__file__).resolve().parents[1] / "manifests"
    return {
        "builtin registry": builtin_manifests(),
        "shipped manifests": load_dir(str(shipped)),
    }


def _port(manifest, direction, capability):
    ports = getattr(manifest, direction)
    return next((port for port in ports if port.capability == capability), None)


@pytest.mark.parametrize("source", ["builtin registry", "shipped manifests"])
def test_replay_contract_declares_canonical_producers_and_consumers(source):
    manifests = {manifest.organ: manifest for manifest in _manifest_sets()[source]}
    crucible = manifests["crucible"]
    mneme = manifests["mneme"]

    template_emit = _port(crucible, "emits", REPLAY_TEMPLATE)
    template_consume = _port(mneme, "consumes", REPLAY_TEMPLATE)
    pack_emit = _port(mneme, "emits", REPLAY_PACK)
    pack_consume = _port(crucible, "consumes", REPLAY_PACK)

    assert template_emit is not None
    assert template_emit.module == "src/crucible/recheck_cmd.py:_write_template"
    assert template_consume is not None
    assert template_consume.module == "src/mneme/replay.py:replay_crucible"
    assert pack_emit is not None
    assert pack_emit.module == "src/mneme/replay.py:replay_crucible"
    assert pack_consume is not None
    assert pack_consume.module == "src/crucible/recheck_cmd.py:_load_replay_pack"


@pytest.mark.parametrize("source", ["builtin registry", "shipped manifests"])
def test_replay_contract_forms_both_directed_edges_and_routes(source):
    mesh = discover(_manifest_sets()[source])
    edges = {
        (edge.producer, edge.consumer, edge.capability)
        for edge in mesh.edges
    }

    assert ("crucible", "mneme", REPLAY_TEMPLATE) in edges
    assert ("mneme", "crucible", REPLAY_PACK) in edges
    assert ("mneme", "crucible", "crucible.thesis/1") in edges
    assert route(mesh, "crucible", "mneme")["path"] == [{
        "producer": "crucible",
        "consumer": "mneme",
        "capability": REPLAY_TEMPLATE,
    }]
    assert route(mesh, "mneme", "crucible")["path"] == [{
        "producer": "mneme",
        "consumer": "crucible",
        "capability": REPLAY_PACK,
    }]


@pytest.mark.parametrize("source", ["builtin registry", "shipped manifests"])
def test_stale_recheck_pack_alias_is_absent(source):
    declared = set()
    for manifest in _manifest_sets()[source]:
        for port in [*manifest.emits, *manifest.consumes]:
            declared.add(port.capability)
            declared.update(port.consumable_as)

    assert STALE_REPLAY_PACK_ALIAS not in declared
