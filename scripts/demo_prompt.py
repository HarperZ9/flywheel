"""demo_prompt.py -- one frozen prompt template per family, plus its sha256.

The certificate BODY shape each template asks for is read from the checker, not
guessed:

  harness/certificates/zarankiewicz.py `_well_formed` requires exactly
  {"m", "n", "s", "t", "edges", "edge_count"}, edges as [row, col] integer
  pairs, s == t == 2 (the only shape ZarankiewiczOracle.check disposes),
  edge_count == len(edges).

  harness/certificates/crossing.py `well_formed` requires exactly
  {"n", "edges", "coords", "crossings"}, coords a list of exactly n [x, y]
  integer pairs. `CrossingOracle.instance_binding` also requires "edges" to
  canonicalize to the SAME graph as the instance it was asked about (see
  `binding_keys = ("n", "edges_key")` and `instance_binding` in that module),
  so the template hands the candidate the exact edge list to copy back rather
  than asking it to reconstruct the graph from a description.

Two family keys are used throughout this driver, and they are the checkers'
own `family` class attribute, not the prereg's longer criterion_id:
ZarankiewiczOracle.family == "zarankiewicz",
CrossingOracle.family == "rectilinear_crossing".

The template TEXT is frozen once it is used against a live model: its sha256
becomes the pinned `prompt_template_sha256` fingerprint field in
harness/pool.py's FINGERPRINT_FIELDS. `template_sha256` hashes the raw
template string itself (the unrendered text, placeholders and all), never a
rendered prompt, so the pinned value does not move when the same template is
rendered against a different instance.
"""
from __future__ import annotations

import hashlib
import json

ZARANKIEWICZ_FAMILY = "zarankiewicz"
CROSSING_FAMILY = "rectilinear_crossing"

_JSON_SEP = (",", ":")  # deterministic: no incidental whitespace in the hash


def _json(obj) -> str:
    return json.dumps(obj, separators=_JSON_SEP)


# --- the two frozen templates ------------------------------------------------
#
# Literal JSON braces are doubled ({{ }}) because these are str.format templates;
# {m}, {n}, ... are the only real substitution points.

_ZARANKIEWICZ_TEMPLATE = """You are given a bipartite graph verification puzzle.

Grid size: {m} rows (numbered 0 through {m_minus_1}) by {n} columns \
(numbered 0 through {n_minus_1}).

Forbidden pattern: no two columns may share two or more rows in common. Two \
columns sharing two rows would form a K_2,2 (a complete bipartite 2-by-2 \
subgraph), which is not allowed anywhere in your answer.

Goal: submit as many row-column edges as possible while keeping the graph \
free of that forbidden pattern.

A valid starting graph (a "star": one row joined to every column) is:
{seed_edges_json}

You may keep, extend, or replace these edges with a larger K_2,2-free graph.

Respond with a single JSON object and NOTHING else: no markdown code fences, \
no explanation, no text before or after the JSON.

The JSON object must have exactly these fields:
{{"m": {m}, "n": {n}, "s": 2, "t": 2, "edges": [[row, col], ...], \
"edge_count": <number of edges>}}

Rules:
- Every edge is a two-element list [row, col] with 0 <= row < {m} and \
0 <= col < {n}.
- No duplicate edges.
- No two columns may share two or more rows.
- "edge_count" must equal the number of edges listed in "edges".
- "s" must be 2 and "t" must be 2.
- Output valid JSON only.
"""

_CROSSING_TEMPLATE = """You are given a graph-drawing verification puzzle.

The graph has {n} vertices, numbered 0 through {n_minus_1}, and these edges:
{edges_json}

Your task: choose integer (x, y) coordinates for every vertex, draw each \
edge as a straight line segment between its two endpoints, and report how \
many pairs of edges cross.

Two edges "cross" only if they intersect at a point strictly inside both \
segments; edges that share an endpoint never count as crossing. No two \
vertices may share the same coordinates, and no three vertices may be \
collinear (exactly on one straight line) -- either of those makes the \
drawing invalid.

Try to choose coordinates that make the crossing count as small as possible.

Respond with a single JSON object and NOTHING else: no markdown code fences, \
no explanation, no text before or after the JSON.

The JSON object must have exactly these fields:
{{"n": {n}, "edges": {edges_json}, "coords": [[x, y], ...], \
"crossings": <a non-negative integer, the count of crossing pairs>}}

Rules:
- "edges" must be exactly the edge list given above, unchanged.
- "coords" must be a list of exactly {n} integer [x, y] pairs, one per \
vertex in order (coords[i] is the position of vertex i).
- No two entries of "coords" may be equal, and no three may be collinear.
- "crossings" must equal the true number of crossing edge pairs for the \
coordinates you chose.
- Output valid JSON only.
"""

TEMPLATES = {
    ZARANKIEWICZ_FAMILY: _ZARANKIEWICZ_TEMPLATE,
    CROSSING_FAMILY: _CROSSING_TEMPLATE,
}


class PromptError(ValueError):
    """An unknown family, or an instance missing a field its template needs."""


def template_sha256(family: str) -> str:
    """sha256 of the frozen template TEXT itself, not of any rendered prompt.

    This is the value that goes into `prompt_template_sha256` in
    harness/pool.py's fingerprint: pinning the template rather than the
    per-instance prompt is what lets the same pin cover all 60 instances of a
    family with one hash.
    """
    if family not in TEMPLATES:
        raise PromptError(
            f"unknown family {family!r}; supported are {sorted(TEMPLATES)}")
    return "sha256:" + hashlib.sha256(
        TEMPLATES[family].encode("utf-8")).hexdigest()


def render_prompt(family: str, instance: dict) -> str:
    """Turn a generator instance dict into the exact prompt string sent to the
    model. Pure and deterministic: the same (family, instance) always renders
    the same text, which is what makes prompt_sha256 in the pool index
    meaningful as a cache key.
    """
    if family == ZARANKIEWICZ_FAMILY:
        return _render_zarankiewicz(instance)
    if family == CROSSING_FAMILY:
        return _render_crossing(instance)
    raise PromptError(
        f"unknown family {family!r}; supported are {sorted(TEMPLATES)}")


def _render_zarankiewicz(instance: dict) -> str:
    try:
        m, n = int(instance["m"]), int(instance["n"])
    except KeyError as e:
        raise PromptError(f"zarankiewicz instance missing field {e}") from e
    seed_edges = instance.get("seed_edges", [])
    return _ZARANKIEWICZ_TEMPLATE.format(
        m=m, n=n, m_minus_1=m - 1, n_minus_1=n - 1,
        seed_edges_json=_json([list(e) for e in seed_edges]),
    )


def _render_crossing(instance: dict) -> str:
    try:
        n = int(instance["n"])
        edges = instance["edges"]
    except KeyError as e:
        raise PromptError(f"crossing instance missing field {e}") from e
    edges_json = _json([list(e) for e in edges])
    return _CROSSING_TEMPLATE.format(n=n, n_minus_1=n - 1, edges_json=edges_json)
