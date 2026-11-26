"""Known-answer and planted-failure tests for video motion-law extraction (Wave 31E)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from gather.deconstruct.video_media_deconstruct import (
    _probe_video,
    compute_motion_law_from_frames,
    read_pgm_luminance,
)


def _write_pgm(path: Path, width: int, height: int, fill_byte: int) -> Path:
    header = f"P5\n# synthetic test frame\n{width} {height}\n255\n".encode("ascii")
    path.write_bytes(header + bytes([fill_byte]) * (width * height))
    return path


def test_static_vs_moving_synthetic_frames_produce_distinct_motion_stats(tmp_path: Path) -> None:
    static_frames = [_write_pgm(tmp_path / f"static_{i}.pgm", 16, 8, 64) for i in range(4)]
    static_stats = compute_motion_law_from_frames(static_frames)
    assert static_stats["frame_count"] == 4
    assert static_stats["motion_energy_mean"] == 0.0
    assert static_stats["motion_energy_peak"] == 0.0
    assert static_stats["scene_cuts"] == []
    assert "still_light_moving_weather" in static_stats["motion_law_tags"]

    moving_levels = [30, 35, 220, 225]  # sharp scene cut between frame 1 and frame 2
    moving_frames = [_write_pgm(tmp_path / f"move_{i}.pgm", 16, 8, lv) for i, lv in enumerate(moving_levels)]
    moving_stats = compute_motion_law_from_frames(moving_frames)
    assert moving_stats["frame_count"] == 4
    assert moving_stats["motion_energy_peak"] > 0.65
    assert moving_stats["motion_energy_mean"] > static_stats["motion_energy_mean"]
    assert moving_stats["scene_cuts"] == [2]
    assert "order_of_change" in moving_stats["motion_law_tags"]
    assert "burst_and_decay" in moving_stats["motion_law_tags"]


def test_probe_video_computes_real_motion_stats_when_ffmpeg_extracts_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mp4 = tmp_path / "clip.mp4"
    fake_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}" if name in ("ffprobe", "ffmpeg") else None)

    def _fake_run(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "ffprobe" in cmd[0]:
            payload = {
                "format": {"duration": "2.0"},
                "streams": [{"codec_type": "video", "codec_name": "h264", "width": 320, "height": 180}],
            }
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        # Simulate ffmpeg emitting 4 PGM frames with a sharp cut at frame 2.
        pattern_path = Path(cmd[-1])
        for idx, lv in enumerate((25, 30, 230, 235), start=1):
            _write_pgm(pattern_path.parent / f"{fake_mp4.stem}_frame_{idx:04d}.pgm", 32, 18, lv)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", _fake_run)
    res = _probe_video(fake_mp4, out_dir)
    assert res["ffprobe_available"] is True and res["ffmpeg_available"] is True
    assert res["codec"] == "h264" and res["width"] == 320 and res["height"] == 180
    # Must NOT be the old empty compute_motion_law_stats([]) bug!
    assert res["motion"]["frame_count"] == 4
    assert res["motion"]["motion_energy_peak"] > 0.7
    assert res["motion"]["scene_cuts"] == [2]
    assert "order_of_change" in res["motion"]["motion_law_tags"]


def test_probe_video_degrades_gracefully_without_ffmpeg_and_bad_pgm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = tmp_path / "not_a_pgm.pgm"
    bad.write_bytes(b"BADHEADER")
    assert read_pgm_luminance(bad) == []

    monkeypatch.setattr("shutil.which", lambda _name: None)
    fake_mp4 = tmp_path / "silent.mp4"
    fake_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    res = _probe_video(fake_mp4, None)
    assert res["ffprobe_available"] is False and res["ffmpeg_available"] is False
    assert res["motion"]["frame_count"] == 0
    assert res["motion"]["motion_law_tags"] == ["static_still"]
