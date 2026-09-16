from types import SimpleNamespace

from harness.live_screen_sources import (
    coherence_capture_source,
    coherence_source_descriptors,
)


class _FakeNative:
    created = []

    @staticmethod
    def capture_available():
        return True

    class RawScreenCaptureSource:
        def __init__(self, region=None, source_id="screen-raw"):
            _FakeNative.created.append(("raw", region, source_id))

    class ScreenCaptureSource:
        def __init__(self, region=None, source_id="screen"):
            _FakeNative.created.append(("png", region, source_id))


def _importer(name):
    assert name == "coherence_membrane.native_capture"
    return _FakeNative


def test_missing_coherence_backend_returns_typed_unavailable_source():
    def missing(_name):
        raise ModuleNotFoundError("coherence_membrane")

    sources = coherence_source_descriptors(import_module=missing, platform="win32")
    assert sources == [{
        "source_id": "display:primary",
        "kind": "display",
        "label": "Primary display",
        "bounds": None,
        "backend": "coherence_membrane.native_capture",
        "available": False,
        "unavailable_reason": "coherence_membrane is not installed",
    }]


def test_coherence_adapter_exposes_plural_display_and_window_descriptors_without_capture():
    sources = coherence_source_descriptors(
        import_module=_importer, platform="win32",
        monitor_rects=[(0, 0, 1920, 1080), (1920, 0, 1280, 720)],
        window_rects=[("0xabc", "Editor", (40, 50, 800, 600))],
    )

    assert [s["source_id"] for s in sources] == ["display:0", "display:1", "window:0xabc"]
    assert sources[1]["bounds"] == (1920, 0, 1280, 720)
    assert sources[2]["kind"] == "window"
    assert sources[2]["label"] == "Editor"
    assert sources[2]["available"] is False
    assert sources[2]["unavailable_reason"] == "window-only capture backend is not implemented"

    source = coherence_capture_source(sources[1], import_module=_importer)
    assert isinstance(source, _FakeNative.ScreenCaptureSource)
    assert _FakeNative.created[-1] == ("png", (1920, 0, 1280, 720), "display:1")


def test_unavailable_window_source_is_not_constructed():
    source = {"source_id": "window:missing", "kind": "window", "label": "Missing",
              "bounds": None, "backend": "coherence_membrane.native_capture",
              "available": False, "unavailable_reason": "window missing"}
    result = coherence_capture_source(source, import_module=lambda _name: SimpleNamespace())
    assert result is None
