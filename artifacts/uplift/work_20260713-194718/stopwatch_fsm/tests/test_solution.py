import pytest
from solution import stopwatch as f
def test_empty(): assert f([]) == (0, [])
def test_one_segment(): assert f([(0, 'start'), (5, 'stop')]) == (5, [])
def test_laps(): assert f([(0, 'start'), (3, 'lap'), (5, 'stop'), (7, 'start'), (9, 'lap'), (10, 'stop')]) == (8, [3, 7])
def test_reset(): assert f([(0, 'start'), (5, 'stop'), (6, 'reset'), (7, 'start'), (9, 'stop')]) == (2, [])
def test_running_at_end(): assert f([(0, 'start')]) == (0, [])
def test_double_start():
    with pytest.raises(ValueError) as e: f([(0, 'start'), (1, 'start')])
    assert str(e.value) == 'already running'
def test_stop_stopped():
    with pytest.raises(ValueError) as e: f([(0, 'stop')])
    assert str(e.value) == 'not running'
def test_lap_stopped():
    with pytest.raises(ValueError) as e: f([(0, 'lap')])
    assert str(e.value) == 'not running'
def test_reset_running():
    with pytest.raises(ValueError) as e: f([(0, 'start'), (1, 'reset')])
    assert str(e.value) == 'still running'
def test_time_warp():
    with pytest.raises(ValueError) as e: f([(0, 'start'), (0, 'stop')])
    assert str(e.value) == 'time warp'
def test_bad_op():
    with pytest.raises(ValueError) as e: f([(0, 'go')])
    assert str(e.value) == 'bad event'
