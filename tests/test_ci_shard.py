"""Sharding may be unbalanced. It may not lose a file.

The whole-suite job exists so a regression cannot hide in a file the curated
slice does not name. Sharding it introduces a new way to recreate that blind
spot: drop a file from every shard and all shards still report green. So
coverage is the invariant under test, and balance is only checked loosely.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_shard", ROOT / "scripts" / "ci_shard.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


def fake_tests(tmp_path, spec: dict):
    """spec: {filename: number_of_test_functions}"""
    for name, n in spec.items():
        body = "".join(f"def test_{i}():\n    pass\n\n" for i in range(n))
        (tmp_path / name).write_text(body or "x = 1\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("count", [1, 2, 3, 4, 7, 16])
def test_every_file_lands_in_exactly_one_shard(count):
    """The property that makes sharding safe, over the REAL test tree."""
    files = S.test_files()
    buckets = S.shard(files, count)
    flat = [p for b in buckets for p in b]
    assert sorted(flat) == sorted(files), "a file was dropped or duplicated"
    assert len(flat) == len(set(flat)), "a file appears in two shards"


def test_no_shard_is_empty_when_there_is_work_for_it():
    """An empty shard means a wasted job and, more importantly, that the
    balancer is not doing what the matrix assumes."""
    files = S.test_files()
    for count in (2, 4):
        buckets = S.shard(files, count)
        assert all(b for b in buckets), f"empty shard at count={count}"


def test_sharding_is_deterministic():
    """Two machines must shard identically, or a file could be skipped by one
    runner and duplicated by another."""
    a = [[p.as_posix() for p in b] for b in S.shard(S.test_files(), 4)]
    b = [[p.as_posix() for p in b] for b in S.shard(S.test_files(), 4)]
    assert a == b


def test_balance_is_reasonable():
    """Not exact, just enough that no shard becomes the new bottleneck. Weight is
    a test-count proxy, so this is deliberately loose."""
    files = S.test_files()
    buckets = S.shard(files, 4)
    loads = [sum(S.weight(p) for p in b) for b in buckets]
    assert min(loads) > 0
    assert max(loads) <= 2 * min(loads), f"shards badly unbalanced: {loads}"


def test_heaviest_file_does_not_stack_with_other_heavy_files(tmp_path):
    """Greedy longest-first must spread the big ones, not clump them."""
    d = fake_tests(tmp_path, {"test_a.py": 100, "test_b.py": 90,
                              "test_c.py": 80, "test_d.py": 1})
    buckets = S.shard(S.test_files(d), 3)
    loads = sorted(sum(S.weight(p) for p in b) for b in buckets)
    # 100, 90 and 80 each open a bucket; the stray 1 joins the lightest of them.
    assert loads == [81, 90, 100], loads


def test_a_new_test_file_cannot_escape_every_shard(tmp_path):
    """The regression this guards: adding a file and having no shard run it."""
    d = fake_tests(tmp_path, {"test_a.py": 3, "test_b.py": 2})
    before = S.test_files(d)
    (d / "test_newcomer.py").write_text("def test_x():\n    pass\n",
                                        encoding="utf-8")
    after = S.test_files(d)
    assert len(after) == len(before) + 1
    flat = [p for b in S.shard(after, 4) for p in b]
    assert (d / "test_newcomer.py") in flat


def test_pycache_is_not_collected(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "test_stale.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (tmp_path / "test_real.py").write_text("def test_y(): pass\n", encoding="utf-8")
    assert [p.name for p in S.test_files(tmp_path)] == ["test_real.py"]


def test_weight_counts_async_tests_too(tmp_path):
    p = tmp_path / "test_a.py"
    p.write_text("def test_one(): pass\nasync def test_two(): pass\n",
                 encoding="utf-8")
    assert S.weight(p) == 2


def test_an_out_of_range_index_is_refused():
    with pytest.raises(ValueError):
        S.shard(S.test_files(), 0)


def test_the_shard_matrix_in_ci_matches_the_count_used():
    """If ci.yml's matrix and its --count ever disagree, some files run twice and
    others never run at all. Both numbers live in the same file; this checks they
    agree."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    import re
    m = re.search(r"shard:\s*\[([^\]]+)\]", ci)
    if not m:
        pytest.skip("no shard matrix in ci.yml")
    indices = sorted(int(x.strip().strip('"\'')) for x in m.group(1).split(","))
    counts = {int(c) for c in re.findall(r"--count\s+(\d+)", ci)}
    assert len(counts) == 1, f"ci.yml uses more than one shard count: {counts}"
    count = counts.pop()
    assert indices == list(range(count)), (
        f"matrix is {indices} but --count is {count}; "
        "some files would run twice and others not at all")
