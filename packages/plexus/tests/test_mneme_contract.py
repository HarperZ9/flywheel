"""Mneme public-main contract falsifiers for Plexus declarations."""
from pathlib import Path

import pytest

from plexus.registry import builtin_manifests, load_dir


MNEME_CRUCIBLE_EXPORT = "mneme.crucible-export/2"
STALE_MNEME_CRUCIBLE_EXPORT = "mneme.crucible-export/1"
LOCAL_ORIGIN_RECHECK = "mneme.local-origin-recheck/1"
CRUCIBLE_THESIS = "crucible.thesis/1"


def _manifest_sets():
    shipped = Path(__file__).resolve().parents[1] / "manifests"
    return {
        "builtin registry": builtin_manifests(),
        "shipped manifests": load_dir(str(shipped)),
    }


def _mneme(manifests):
    return next(manifest for manifest in manifests if manifest.organ == "mneme")


def _capabilities(manifest):
    declared = set()
    for port in [*manifest.emits, *manifest.consumes]:
        declared.add(port.capability)
        declared.update(port.consumable_as)
    return declared


def _emit(manifest, capability):
    return next((port for port in manifest.emits if port.capability == capability), None)


@pytest.mark.parametrize("source", ["builtin registry", "shipped manifests"])
def test_mneme_declares_schema_v2_crucible_export_and_not_stale_v1(source):
    mneme = _mneme(_manifest_sets()[source])
    declared = _capabilities(mneme)
    export = _emit(mneme, MNEME_CRUCIBLE_EXPORT)

    assert export is not None
    assert export.module == "src/mneme/compose.py:to_crucible_thesis"
    assert "declarative mneme.recheck/1 descriptors" in export.summary
    assert CRUCIBLE_THESIS in export.consumable_as
    assert STALE_MNEME_CRUCIBLE_EXPORT not in declared


@pytest.mark.parametrize("source", ["builtin registry", "shipped manifests"])
def test_mneme_declares_local_origin_recheck_as_terminal_capability(source):
    mneme = _mneme(_manifest_sets()[source])
    origin = _emit(mneme, LOCAL_ORIGIN_RECHECK)

    assert origin is not None
    assert origin.module == "src/mneme/origin.py:recheck_local_origins"
    assert "caller-approved root" in origin.summary
    assert origin.consumable_as == ()
    assert "src/mneme/origin.py" in mneme.evidence
    assert "tests/test_crucible_replay.py" in mneme.evidence
