"""Falsifiers for the render + run surfaces (graph export, pipeline script).

Load-bearing: (1) Mermaid/DOT export names every organ and labels every edge with
its capability, and marks self-loops distinctly; (2) the pipeline script is a
runnable, ordered invocation that ends at the target and surfaces feedback loops
as a comment rather than a false linear order.
"""
from plexus.graph import to_dot, to_mermaid
from plexus.mesh import discover
from plexus.registry import builtin_manifests
from plexus.run import pipeline_script


def _mesh():
    return discover(builtin_manifests())


def test_mermaid_names_organs_and_labels_edges():
    m = to_mermaid(_mesh())
    assert m.startswith("flowchart LR")
    for organ in ("gather", "crucible", "mneme", "index", "forum"):
        assert f'{organ}["{organ}"]' in m
    assert '-->|"gather.digest/1"| crucible' in m          # a real cross-tool edge, labelled
    assert "-.->" in m                                     # index self-loops rendered dotted


def test_dot_is_a_digraph_with_labelled_edges():
    d = to_dot(_mesh())
    assert d.startswith("digraph plexus {") and d.rstrip().endswith("}")
    assert '"gather" -> "crucible" [label="gather.digest/1"]' in d
    assert "style=dotted" in d                             # self-loop styling present


def test_pipeline_script_is_runnable_ordered_and_ends_at_target():
    s = pipeline_script(_mesh(), "crucible")
    assert s.startswith("#!/usr/bin/env bash")
    assert "# plexus pipeline to feed: crucible" in s
    lines = [ln for ln in s.splitlines() if ln and not ln.startswith("#")]
    assert lines[-1].strip() == "crucible run"            # target invoked last
    assert "gather run" in s                              # an upstream source is invoked


def test_pipeline_script_surfaces_the_feedback_loop():
    s = pipeline_script(_mesh(), "crucible")
    assert "feedback loop" in s and "crucible <-> index" in s


def test_pipeline_script_reports_unknown_target():
    assert "error" in pipeline_script(_mesh(), "nope")
