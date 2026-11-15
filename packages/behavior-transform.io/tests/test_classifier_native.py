# CALIBRATED VIEW
# audit_counts: {}
#
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def test_no_warden_shell_after_classifier_import():
    """classifier.py must not trigger new warden_shell imports."""
    # Snapshot before import — editable-install finders are already registered
    before = set(sys.modules.keys())
    import classifier  # noqa: F401 — side-effect import
    after = set(sys.modules.keys())
    new_modules = after - before
    warden_hits = [m for m in new_modules if "warden_shell" in m and "_finder" not in m]
    assert warden_hits == [], f"classifier.py pulled in warden_shell modules: {warden_hits}"


def test_calibration_pipeline_instantiates():
    import classifier
    pipeline = classifier.CalibrationPipeline()
    assert pipeline is not None
