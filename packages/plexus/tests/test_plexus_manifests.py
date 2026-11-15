"""Dogfood falsifier: the built-in registry must survive a round-trip through the
public *.interop.json format with the discovered mesh unchanged. If it does not,
the format cannot faithfully represent what a flagship ships — which is the whole
premise of decentralized discovery.
"""
from pathlib import Path

from plexus.manifest import content_hash
from plexus.mesh import discover
from plexus.registry import builtin_manifests, export_all, load_dir


def _edgeset(manifests):
    return {(e.producer, e.consumer, e.capability) for e in discover(manifests).edges}


def test_builtin_manifests_roundtrip_through_json(tmp_path):
    written = export_all(str(tmp_path))
    assert len(written) == len(builtin_manifests())
    reloaded = load_dir(str(tmp_path))
    assert {m.organ for m in reloaded} == {m.organ for m in builtin_manifests()}
    # the mesh discovered from the JSON files is identical to the in-code mesh
    assert _edgeset(reloaded) == _edgeset(builtin_manifests())


def test_exported_files_are_named_per_organ(tmp_path):
    export_all(str(tmp_path))
    names = {p.name for p in tmp_path.glob("*.interop.json")}
    expected = {f"{m.organ}.interop.json" for m in builtin_manifests()}
    assert names == expected


def test_shipped_manifests_match_the_full_builtin_registry_content():
    manifest_dir = Path(__file__).resolve().parents[1] / "manifests"
    builtin = {manifest.organ: manifest for manifest in builtin_manifests()}
    shipped = {manifest.organ: manifest for manifest in load_dir(str(manifest_dir))}

    assert set(shipped) == set(builtin)
    for organ in sorted(builtin):
        assert shipped[organ].to_dict() == builtin[organ].to_dict()
        assert content_hash(shipped[organ]) == content_hash(builtin[organ])
