import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from categories import (
    HarmCategory,
    CategoryDetection,
    DetectionResult,
    CategoryDetector,
    category_detector,
    detect_categories,
)


def test_harm_category_has_14_members():
    assert len(HarmCategory) == 14


def test_category_detection_detected_above_threshold():
    d = CategoryDetection(category=HarmCategory.ILLEGAL, severity=0.5, tier=1)
    assert d.detected is True


def test_category_detection_not_detected_below_threshold():
    d = CategoryDetection(category=HarmCategory.ILLEGAL, severity=0.10, tier=1)
    assert d.detected is False


def test_category_detection_none_category():
    d = CategoryDetection(category=None, severity=0.5, tier=1)
    assert d.detected is False


def test_tier0_detection_threshold():
    d = CategoryDetection(category=HarmCategory.HAZMAT, severity=0.05, tier=0)
    assert d.detected is False
    d2 = CategoryDetection(category=HarmCategory.HAZMAT, severity=0.60, tier=0)
    assert d2.detected is True


def test_tier2_threshold():
    d = CategoryDetection(category=HarmCategory.HATEFUL, severity=0.20, tier=2)
    assert d.detected is False
    d2 = CategoryDetection(category=HarmCategory.HATEFUL, severity=0.30, tier=2)
    assert d2.detected is True


def test_tier3_threshold():
    d = CategoryDetection(category=HarmCategory.DANGEROUS, severity=0.20, tier=3)
    assert d.detected is False
    d2 = CategoryDetection(category=HarmCategory.DANGEROUS, severity=0.30, tier=3)
    assert d2.detected is True


def test_detector_tier_map_t0_has_six():
    d = CategoryDetector()
    tiers = d._build_category_tiers()
    t0_cats = [c for c, t in tiers.items() if t == 0]
    assert len(t0_cats) == 6


def test_detector_tier_map_t1_has_two():
    d = CategoryDetector()
    tiers = d._build_category_tiers()
    t1_cats = [c for c, t in tiers.items() if t == 1]
    assert len(t1_cats) == 2


def test_detector_tier_map_t2_has_four():
    d = CategoryDetector()
    tiers = d._build_category_tiers()
    t2_cats = [c for c, t in tiers.items() if t == 2]
    assert len(t2_cats) == 4


def test_detector_tier_map_t3_has_two():
    d = CategoryDetector()
    tiers = d._build_category_tiers()
    t3_cats = [c for c, t in tiers.items() if t == 3]
    assert len(t3_cats) == 2


def test_detect_clean_text_no_rewrite():
    d = CategoryDetector()
    result = d.detect("the weather is sunny and warm today")
    assert not result.required_rewrite
    assert result.audit_trail.get("status") == "clean"


def test_detect_returns_detection_result():
    d = CategoryDetector()
    result = d.detect("some text")
    assert isinstance(result, DetectionResult)
    assert isinstance(result.detections, list)
    assert len(result.detections) == 14


def test_detect_categories_convenience():
    result = detect_categories("clean ordinary text")
    assert isinstance(result, DetectionResult)
    assert not result.required_rewrite


def test_category_detector_singleton():
    d1 = category_detector()
    d2 = category_detector()
    assert d1 is d2


def test_detection_result_properties():
    result = DetectionResult(
        original="test", rewritten="test", detections=[]
    )
    assert result.required_rewrite is False
    assert result.blocked is False


def test_tier_thresholds_match():
    d = CategoryDetector()
    assert d.TIER_THRESHOLDS == {0: 0.65, 1: 0.15, 2: 0.25, 3: 0.25}


def test_tier_weights_match():
    d = CategoryDetector()
    assert d.TIER_WEIGHTS == {0: 0.6, 1: 0.5, 2: 0.4, 3: 0.4}
