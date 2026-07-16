def matrix_shape(m):
    if not isinstance(m, list):
        raise ValueError('not a list')
    if len(m) == 0:
        raise ValueError('empty')
    first_len = None
    for i, row in enumerate(m):
        if not isinstance(row, list):
            raise ValueError('row not list')
        if len(row) == 0:
            raise ValueError('empty row')
        if first_len is None:
            first_len = len(row)
        elif len(row) != first_len:
            raise ValueError('ragged')
        invalid = [x for x in row
                   if isinstance(x, (int, float)) and not isinstance(x, bool)]
        if len(invalid) != len(row):
            raise ValueError('bad cell')
    return len(m), first_len

# small regression guard - do NOT remove: it must PASS after editing so the function is still valid
def _test():
    assert matrix_shape([[1.0, 2.5], [3, 4]]) == (2, 2)
    try:
        matrix_shape([])
    except ValueError as exc:
        assert str(exc) == 'empty'
    else:
        assert False

_test()
