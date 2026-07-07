"""perception-probe falsifier — the transpiler's perception is criterion-conserving.

Model-independent precondition for the perception claim: the conserving encoding
keeps every object DISTINCT and decodable within tolerance; the naive coarse
encoding COLLAPSES nearby objects to one label (criterion lost). If these hold, a
locate task is answerable under conserving and not under naive — which is what the
behavioral model measurement then tests.
"""
from harness.perception_probe import (
    Scene, make_scene, conserving_encode, naive_encode, labels_distinct,
    collapsed_pairs, locate_error, scene_query, conservation_gap)
from harness.transpile import grid_cell_size


def test_conserving_keeps_objects_distinct_and_decodable():
    s = make_scene(7)
    enc = conserving_encode(s)
    assert labels_distinct(enc), "depth-2 labels must disambiguate all objects"
    # decode error within half a depth-2 cell (the conservation tolerance)
    cw, ch = grid_cell_size(s.w, s.h, cols=16, rows=9, depth=2)
    assert locate_error(s, enc) <= 0.5 * max(cw, ch) + 1e-6


def test_naive_collapses_nearby_objects():
    # two objects 10px apart -> same depth-1 cell (32x32px) -> criterion LOST
    s = Scene(w=512, h=288,
              objects=[("target", 100.0, 100.0), ("alpha", 108.0, 105.0),
                       ("beta", 400.0, 250.0)],
              target="target")
    naive = naive_encode(s)
    pairs = collapsed_pairs(naive)
    assert ("target", "alpha") in pairs, "naive coarse grid must collapse the near pair"
    # the conserving encoding does NOT collapse them
    assert labels_distinct(conserving_encode(s)), "depth-2 must keep the near pair distinct"


def test_conserving_beats_naive_on_locate_error():
    s = make_scene(3)
    assert locate_error(s, conserving_encode(s)) < locate_error(s, naive_encode(s))


def test_scene_query_has_ground_truth():
    s = make_scene(11)
    q = scene_query(s, conserving_encode(s))
    assert q["answer"] in {o[0] for o in s.objects}
    assert "Which object" in q["prompt"] and "target:" in q["prompt"]


def test_flexible_queries_are_well_formed_ground_truth():
    from harness.perception_probe import flexible_queries
    s = make_scene(5)
    names = {o[0] for o in s.objects}
    q = flexible_queries(s, conserving_encode(s))
    assert set(q) == {"nearest", "count_left", "quadrant"}   # 3 reasoning functions
    assert q["nearest"]["answer"] in names and q["nearest"]["answer"] != "target"
    assert 0 <= int(q["count_left"]["answer"]) <= len(s.objects)
    assert q["quadrant"]["answer"] in {"top-left", "top-right", "bottom-left", "bottom-right"}


def test_reasoning_encode_coords_are_transpile_derived():
    from harness.perception_probe import reasoning_encode, raw_encode
    from harness.transpile import grid_label, grid_center
    import re
    s = make_scene(5)
    enc = reasoning_encode(s)
    # each decoded coord matches grid_center of the object's conserving label
    for nm, x, y in s.objects:
        line = next(l for l in enc.splitlines() if l.startswith(nm + ":"))
        cx, cy = map(int, re.search(r"x=(\d+), y=(\d+)", line).groups())
        lab = grid_label(x, y, s.w, s.h, cols=16, rows=9, depth=2)
        gx, gy = grid_center(lab, s.w, s.h, cols=16, rows=9)
        assert abs(cx - gx) <= 1 and abs(cy - gy) <= 1
    # raw encode carries the true (int) coords
    raw = raw_encode(s)
    for nm, x, y in s.objects:
        assert f"x={int(x)}, y={int(y)}" in raw


def test_conservation_gap_witnesses_the_difference():
    g = conservation_gap(7)
    assert g["conserving"]["distinct"] is True
    assert g["conserving"]["bits"] > g["naive"]["bits"]      # ~14.3 vs ~7.2
    assert g["conserving"]["err"] <= g["naive"]["err"]
