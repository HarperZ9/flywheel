"""The creative graph must be a Merkle DAG, not a diagram: deterministic
outputs under one graph id, branch/merge that actually composites, chains
that move only downstream of a change, and named refusals for cycles,
dangling edges, wrong arity, and unknown ops."""

import base64
import io

import pytest

pytest.importorskip("PIL")

from harness.creative_graph import run_graph


def _branchy(seed_a=58, seed_b=59):
    return (
        [
            {"id": "w", "op": "wireframe",
             "args": {"primitive": "orbit-sphere", "seed": seed_a,
                      "width": 240, "height": 160}},
            {"id": "p", "op": "plate",
             "args": {"seed": seed_b, "width": 240, "height": 160}},
            {"id": "m", "op": "blend", "args": {"alpha": 0.5}},
            {"id": "f", "op": "film_frame",
             "args": {"seed": 58, "grain": 0.2, "letterbox": True}},
        ],
        [
            {"from": "w", "to": "m"},
            {"from": "p", "to": "m"},
            {"from": "m", "to": "f"},
        ],
    )


def test_a_branching_graph_runs_and_re_derives():
    nodes, edges = _branchy()
    a = run_graph(nodes, edges)
    assert not a["refused"], a["refusals"]
    b = run_graph(nodes, edges)
    assert a["receipt"]["graph_id"] == b["receipt"]["graph_id"]
    assert a["outputs"].keys() == {"f"}
    assert base64.b64decode(a["outputs"]["f"]) == \
        base64.b64decode(b["outputs"]["f"])


def test_changing_one_branch_moves_only_downstream_chains():
    nodes, edges = _branchy(seed_b=59)
    a = run_graph(nodes, edges)
    nodes2, _ = _branchy(seed_b=60)          # reseed the plate branch only
    b = run_graph(nodes2, edges)
    ca = {n["id"]: n["chain"] for n in a["receipt"]["nodes"]}
    cb = {n["id"]: n["chain"] for n in b["receipt"]["nodes"]}
    assert ca["w"] == cb["w"], "the untouched branch must hold"
    assert ca["p"] != cb["p"], "the reseeded branch must move"
    assert ca["m"] != cb["m"] and ca["f"] != cb["f"], \
        "everything downstream of the change must move"
    assert a["receipt"]["graph_id"] != b["receipt"]["graph_id"]


def test_merges_actually_composite():
    from PIL import Image
    nodes = [
        {"id": "a", "op": "plate",
         "args": {"seed": 58, "width": 120, "height": 80}},
        {"id": "b", "op": "plate",
         "args": {"seed": 59, "width": 120, "height": 80}},
        {"id": "s", "op": "beside", "args": {}},
    ]
    edges = [{"from": "a", "to": "s"}, {"from": "b", "to": "s"}]
    out = run_graph(nodes, edges)
    assert not out["refused"]
    im = Image.open(io.BytesIO(base64.b64decode(out["outputs"]["s"])))
    assert im.size == (240, 80), "beside doubles the width"
    # difference of a plate with itself is black
    nodes2 = [
        {"id": "a", "op": "plate",
         "args": {"seed": 58, "width": 120, "height": 80}},
        {"id": "b", "op": "plate",
         "args": {"seed": 58, "width": 120, "height": 80}},
        {"id": "d", "op": "difference", "args": {}},
    ]
    out2 = run_graph(nodes2,
                     [{"from": "a", "to": "d"}, {"from": "b", "to": "d"}])
    im2 = Image.open(io.BytesIO(base64.b64decode(out2["outputs"]["d"])))
    assert im2.convert("L").getextrema() == (0, 0), \
        "identical inputs must difference to black"


def test_fan_out_yields_two_sinks():
    nodes = [
        {"id": "src", "op": "plate",
         "args": {"seed": 58, "width": 120, "height": 80}},
        {"id": "f1", "op": "film_frame", "args": {"grain": 0.0}},
        {"id": "f2", "op": "film_frame", "args": {"grain": 0.9}},
    ]
    edges = [{"from": "src", "to": "f1"}, {"from": "src", "to": "f2"}]
    out = run_graph(nodes, edges)
    assert not out["refused"]
    assert set(out["receipt"]["sinks"]) == {"f1", "f2"}
    assert out["outputs"]["f1"] != out["outputs"]["f2"]


def test_named_refusals_at_every_fence():
    assert "at least one" in run_graph([], [])["refusals"][0]
    assert "unknown op" in run_graph(
        [{"id": "x", "op": "teleport"}], [])["refusals"][0]
    assert "duplicate" in run_graph(
        [{"id": "x", "op": "plate"}, {"id": "x", "op": "plate"}],
        [])["refusals"][0]
    assert "does not exist" in run_graph(
        [{"id": "x", "op": "plate"}],
        [{"from": "x", "to": "ghost"}])["refusals"][0]
    assert "takes 2" in run_graph(
        [{"id": "a", "op": "plate"}, {"id": "m", "op": "blend"}],
        [{"from": "a", "to": "m"}])["refusals"][0]
    # two inputs into a one-input transform is an arity refusal
    assert "takes 1" in run_graph(
        [{"id": "a", "op": "plate"},
         {"id": "t1", "op": "film_frame"},
         {"id": "t2", "op": "film_frame"}],
        [{"from": "a", "to": "t1"},
         {"from": "t2", "to": "t1"}])["refusals"][0]
    # a true two-cycle with clean arity is a cycle refusal
    assert "cycle" in run_graph(
        [{"id": "t1", "op": "film_frame"},
         {"id": "t2", "op": "film_frame"}],
        [{"from": "t1", "to": "t2"},
         {"from": "t2", "to": "t1"}])["refusals"][0]
