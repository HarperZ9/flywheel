import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest
from surface_heatmap import SurfaceHeatmap


def test_heatmap_instantiates():
    hm = SurfaceHeatmap()
    assert hm.warm_threshold == 0.7


def test_record_observation():
    hm = SurfaceHeatmap()
    hm.record_observation("test_surface", 0.5, "test reason")
    assert "test_surface" in hm.surfaces
    assert hm.surfaces["test_surface"]["temperature"] == 0.5


def test_measure_all():
    hm = SurfaceHeatmap()
    hm.record_observation("s1", 0.3)
    hm.record_observation("s2", 0.8)
    temps = hm.measure_all()
    assert temps == {"s1": 0.3, "s2": 0.8}


def test_measure_all_empty():
    hm = SurfaceHeatmap()
    assert hm.measure_all() == {}


def test_identify_warm_surfaces():
    hm = SurfaceHeatmap()
    hm.record_observation("cool", 0.3)
    hm.record_observation("warm", 0.8)
    warm = hm.identify_warm_surfaces()
    assert "warm" in warm
    assert "cool" not in warm


def test_identify_warm_custom_threshold():
    hm = SurfaceHeatmap()
    hm.record_observation("mid", 0.5)
    assert hm.identify_warm_surfaces(threshold=0.4) == {"mid": 0.5}
    assert hm.identify_warm_surfaces(threshold=0.6) == {}


def test_set_warm_threshold():
    hm = SurfaceHeatmap()
    hm.set_warm_threshold(0.5)
    assert hm.warm_threshold == 0.5


def test_set_warm_threshold_invalid():
    hm = SurfaceHeatmap()
    with pytest.raises(ValueError):
        hm.set_warm_threshold(1.5)
    with pytest.raises(ValueError):
        hm.set_warm_threshold(-0.1)


def test_cool_surface():
    hm = SurfaceHeatmap()
    hm.record_observation("hot", 0.9)
    hm.cool_surface("hot")
    assert hm.surfaces["hot"]["temperature"] == 0.0


def test_cool_nonexistent_surface():
    hm = SurfaceHeatmap()
    hm.cool_surface("nonexistent")


def test_get_observations():
    hm = SurfaceHeatmap()
    hm.record_observation("s1", 0.5, "first")
    hm.record_observation("s1", 0.7, "second")
    obs = hm.get_observations("s1")
    assert len(obs) == 2
    assert obs[0]["reason"] == "first"


def test_get_observations_nonexistent():
    hm = SurfaceHeatmap()
    assert hm.get_observations("missing") == []
