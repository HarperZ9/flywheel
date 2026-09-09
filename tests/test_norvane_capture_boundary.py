"""Adversarial filesystem and capture-boundary controls, using synthetic data."""
import json

import pytest

from harness import norvane_capture_io as io
from harness.private_artifact_fs import PrivateArtifactError, UNSUPPORTED_FS
from tests.test_norvane_capture import capture, load, rewrite


def test_parent_swap_never_reads_replacement_capture(tmp_path, monkeypatch):
    parent = tmp_path / "parent"
    root = parent / "capture"
    manifest = capture(root)
    replacement = tmp_path / "replacement"
    capture(replacement / "capture", "REPLACEMENT_SECRET")
    real_open = io.open_artifact_root
    attempted = []

    class SwapReader:
        def __enter__(self):
            self.reader = real_open(root, writable=False).__enter__()
            return self

        def __exit__(self, *args):
            self.reader.close()

        def read_bytes(self, name, **kwargs):
            if not attempted:
                attempted.append(True)
                try:
                    parent.rename(tmp_path / "moved")
                    parent.symlink_to(replacement, target_is_directory=True)
                except OSError:
                    # Windows reader handles deny ancestor rename while open.
                    pass
            return self.reader.read_bytes(name, **kwargs)

    monkeypatch.setattr(io, "open_artifact_root", lambda *_a, **_kw: SwapReader())
    try:
        result = load(root, manifest)
    except ValueError:
        result = None
    assert attempted
    if result is not None:
        assert result["manifest_file_consistency"] == "match"


def test_directory_link_rejected(tmp_path):
    root = tmp_path / "capture"
    manifest = capture(root)
    (root / "step-2").rename(tmp_path / "outside")
    try:
        (root / "step-2").symlink_to(tmp_path / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink unavailable")
    with pytest.raises(ValueError, match="^capture input rejected$"):
        load(root, manifest)


def test_unsupported_filesystem_has_no_unsafe_fallback(tmp_path, monkeypatch):
    manifest = capture(tmp_path)
    def unsupported(*args, **kwargs):
        raise PrivateArtifactError(UNSUPPORTED_FS, "DO_NOT_ECHO_SECRET_PATH")
    monkeypatch.setattr(io, "open_artifact_root", unsupported)
    with pytest.raises(ValueError, match="^capture input rejected$"):
        load(tmp_path, manifest)


@pytest.mark.parametrize("field,value", [("num_commands", True), ("steps", 3.0),
                                        ("fix_correct", "true")])
def test_score_types_do_not_coerce(tmp_path, field, value):
    manifest = capture(tmp_path)
    rewrite(tmp_path, "final/score.json", lambda x: x.update({field: value}))
    with pytest.raises(ValueError):
        load(tmp_path, manifest)


def test_total_byte_limit_is_enforced_by_reader(tmp_path, monkeypatch):
    manifest = capture(tmp_path)
    monkeypatch.setattr(io, "MAX_TOTAL", 100)
    with pytest.raises(ValueError):
        load(tmp_path, manifest)


def test_discontinuous_history_is_not_reconstructed(tmp_path):
    manifest = capture(tmp_path)
    rewrite(tmp_path, "step-3/state.json", lambda x: x["commands_executed"].pop(0))
    result = load(tmp_path, manifest)
    assert "state_history_discontinuity" in result["issues"]
    assert "harness_prefix_unconfirmed" in result["issues"]
    assert all(c["origin"] == "unknown" for c in result["commands"])


def test_cli_error_does_not_echo_sensitive_filename(tmp_path, capsys):
    from harness.norvane_capture_cli import main
    assert main([str(tmp_path), "--source-manifest", str(tmp_path / "SECRET_PATH")]) == 2
    result = capsys.readouterr()
    assert json.loads(result.out) == {"error": "capture_input_rejected"}
    assert "SECRET_PATH" not in result.out + result.err
