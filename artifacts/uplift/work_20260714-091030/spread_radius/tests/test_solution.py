import pytest
from solution import spread_radius as f
def test_one_step(): assert f(['S.']) == 1
def test_source_only(): assert f(['S']) == 0
def test_unreachable(): assert f(['S#.']) == -1
def test_square(): assert f(['S..', '...', '...']) == 4
def test_two_sources(): assert f(['S.S']) == 1
def test_two_sources_middle(): assert f(['S...S']) == 2
def test_corridor(): assert f(['S..', '##.', '...']) == 6
def test_no_open_cells(): assert f(['S#']) == 0
def test_ragged():
    with pytest.raises(ValueError) as e: f(['S.', 'S'])
    assert str(e.value) == 'ragged'
def test_bad_cell():
    with pytest.raises(ValueError) as e: f(['SX'])
    assert str(e.value) == 'bad cell'
def test_no_source():
    with pytest.raises(ValueError) as e: f(['...'])
    assert str(e.value) == 'no source'
def test_bad_grid_plain_string():
    with pytest.raises(ValueError) as e: f('S.')
    assert str(e.value) == 'bad grid'
def test_bad_grid_empty():
    with pytest.raises(ValueError): f([])
def test_bad_grid_empty_row():
    with pytest.raises(ValueError): f([''])
def test_bad_grid_row_type():
    with pytest.raises(ValueError): f([1])
