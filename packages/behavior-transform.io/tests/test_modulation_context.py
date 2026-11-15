import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from modulation_context import (
    generate_request_id,
    set_request_id,
    get_request_id,
    set_detection_result,
    get_detection_result,
    clear_context,
)


def test_generate_request_id():
    rid = generate_request_id()
    assert isinstance(rid, str)
    assert len(rid) > 0


def test_generate_request_id_unique():
    rid1 = generate_request_id()
    rid2 = generate_request_id()
    assert rid1 != rid2


def test_set_and_get_request_id():
    rid = generate_request_id()
    set_request_id(rid)
    assert get_request_id() == rid
    clear_context()


def test_get_request_id_default():
    clear_context()
    assert get_request_id() == ""


def test_set_and_get_detection_result():
    from categories import DetectionResult
    detection = DetectionResult(
        original="test", rewritten="test", detections=[]
    )
    set_detection_result(detection)
    assert get_detection_result() is detection
    clear_context()


def test_get_detection_result_default():
    clear_context()
    assert get_detection_result() is None


def test_clear_context():
    set_request_id("test-id")
    clear_context()
    assert get_request_id() == ""
    assert get_detection_result() is None
