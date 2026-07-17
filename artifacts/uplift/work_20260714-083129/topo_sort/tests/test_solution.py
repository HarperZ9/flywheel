from solution import topo_sort as f
def _ok(n, edges, order):
    if order is None or sorted(order) != list(range(n)):
        return False
    pos = {x: i for i, x in enumerate(order)}
    return all(pos[u] < pos[v] for u, v in edges)
def test_empty():
    assert f(0, []) == []
def test_chain():
    assert _ok(3, [[0,1],[1,2]], f(3, [[0,1],[1,2]]))
def test_diamond():
    e=[[0,1],[0,2],[1,3],[2,3]]
    assert _ok(4, e, f(4, e))
def test_cycle():
    assert f(2, [[0,1],[1,0]]) is None
def test_self_loop():
    assert f(1, [[0,0]]) is None
def test_isolated():
    assert _ok(4, [[1,2]], f(4, [[1,2]]))
