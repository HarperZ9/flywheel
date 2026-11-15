"""Tests for the frame-handoff contract and portable capture sources."""

from __future__ import annotations

from coherence_membrane.capture import (
    CallableFrameSource,
    DirectoryFrameSource,
    Frame,
    FrameDescriptor,
    IterableFrameSource,
)


def test_frame_read_from_payload():
    f = Frame(descriptor=FrameDescriptor("s", 0), payload=b"abc")
    assert f.read() == b"abc"


def test_frame_read_from_path(make_png, tmp_path):
    png = make_png(2, 2, bytes(12))
    p = tmp_path / "f.png"
    p.write_bytes(png)
    f = Frame(descriptor=FrameDescriptor("s", 0), path=str(p))
    assert f.read() == png


def test_directory_source_yields_sorted_frames(make_png, tmp_path):
    (tmp_path / "frame_000.png").write_bytes(make_png(2, 2, bytes(12)))
    (tmp_path / "frame_001.png").write_bytes(make_png(2, 2, bytes(12)))
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")
    frames = list(DirectoryFrameSource(tmp_path, pattern="*.png").frames())
    assert len(frames) == 2
    assert [f.descriptor.frame_index for f in frames] == [0, 1]
    assert all(f.descriptor.pixel_format == "png" for f in frames)
    assert frames[0].read() == make_png(2, 2, bytes(12))


def test_callable_source_stops_on_none():
    seq = [b"a", b"b", None]
    it = iter(seq)
    src = CallableFrameSource(lambda: next(it))
    frames = list(src.frames())
    assert [f.read() for f in frames] == [b"a", b"b"]
    assert [f.descriptor.frame_index for f in frames] == [0, 1]


def test_iterable_source_wraps_bytes_and_frames():
    pre = Frame(descriptor=FrameDescriptor("pre", 9), payload=b"z")
    src = IterableFrameSource([b"a", pre])
    frames = list(src.frames())
    assert frames[0].read() == b"a"
    assert frames[1] is pre  # existing Frame passed through unchanged
