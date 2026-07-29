"""demo_prompt.py: the two frozen prompt templates and their sha256.

Loaded from scripts/ the same way tests/test_determinism_pins.py loads
determinism_pins.py: importlib.util.spec_from_file_location, since scripts/ is
not a package (pyproject.toml excludes it from setuptools discovery).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "demo_prompt", ROOT / "scripts" / "demo_prompt.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


ZARANKIEWICZ_INSTANCE = {
    "generator_id": "zarankiewicz.bipartite.v1", "generator_version": 1,
    "seed": 3, "difficulty": 1, "m": 7, "n": 11, "s": 2, "t": 2,
    "seed_edges": [[0, 0], [0, 1], [0, 2]],
}

CROSSING_INSTANCE = {
    "generator_id": "crossing.random_nonplanar.v1", "generator_version": 1,
    "seed": 5, "difficulty": 1, "n": 7,
    "edges": [[0, 1], [1, 2], [2, 3], [0, 3], [0, 2], [1, 4], [4, 5], [5, 6]],
    "euler_lower_bound": 2,
}


# --- template_sha256 ---------------------------------------------------------

def test_template_sha256_is_stable_across_calls():
    assert P.template_sha256("zarankiewicz") == P.template_sha256("zarankiewicz")


def test_template_sha256_differs_between_families():
    assert (P.template_sha256("zarankiewicz")
            != P.template_sha256("rectilinear_crossing"))


def test_template_sha256_hashes_the_raw_template_text_not_a_rendered_prompt():
    """The pinned value must not move when the SAME template is rendered
    against a different instance -- it is a hash of the family's frozen text."""
    expected = "sha256:" + hashlib.sha256(
        P.TEMPLATES["zarankiewicz"].encode("utf-8")).hexdigest()
    assert P.template_sha256("zarankiewicz") == expected

    # Rendering does not touch the pinned hash.
    before = P.template_sha256("zarankiewicz")
    P.render_prompt("zarankiewicz", ZARANKIEWICZ_INSTANCE)
    assert P.template_sha256("zarankiewicz") == before


def test_template_sha256_rejects_an_unknown_family():
    with pytest.raises(P.PromptError, match="unknown family"):
        P.template_sha256("no_such_family")


# --- render_prompt: determinism -----------------------------------------------

def test_render_prompt_is_deterministic():
    a = P.render_prompt("zarankiewicz", ZARANKIEWICZ_INSTANCE)
    b = P.render_prompt("zarankiewicz", ZARANKIEWICZ_INSTANCE)
    assert a == b


def test_render_prompt_rejects_an_unknown_family():
    with pytest.raises(P.PromptError, match="unknown family"):
        P.render_prompt("no_such_family", ZARANKIEWICZ_INSTANCE)


def test_render_prompt_rejects_a_missing_field():
    with pytest.raises(P.PromptError, match="missing field"):
        P.render_prompt("zarankiewicz", {"m": 7})


# --- zarankiewicz: shape asked for must match zarankiewicz.py's _well_formed --

def test_zarankiewicz_prompt_states_the_grid_size():
    text = P.render_prompt("zarankiewicz", ZARANKIEWICZ_INSTANCE)
    assert "7 rows" in text
    assert "11 columns" in text


def test_zarankiewicz_prompt_embeds_the_seed_witness_as_json():
    text = P.render_prompt("zarankiewicz", ZARANKIEWICZ_INSTANCE)
    assert json.dumps(ZARANKIEWICZ_INSTANCE["seed_edges"], separators=(",", ":")) in text


def test_zarankiewicz_prompt_names_every_required_certificate_field():
    text = P.render_prompt("zarankiewicz", ZARANKIEWICZ_INSTANCE)
    for field in ('"m"', '"n"', '"s"', '"t"', '"edges"', '"edge_count"'):
        assert field in text, field


def test_zarankiewicz_prompt_pins_s_and_t_to_two():
    text = P.render_prompt("zarankiewicz", ZARANKIEWICZ_INSTANCE)
    assert '"s": 2' in text and '"t": 2' in text


def test_zarankiewicz_prompt_forbids_extra_prose():
    text = P.render_prompt("zarankiewicz", ZARANKIEWICZ_INSTANCE)
    assert "NOTHING else" in text
    assert "JSON only" in text


# --- crossing: shape asked for must match crossing.py's well_formed ----------

def test_crossing_prompt_states_vertex_count():
    text = P.render_prompt("rectilinear_crossing", CROSSING_INSTANCE)
    assert "7 vertices" in text


def test_crossing_prompt_embeds_the_exact_edge_list_as_json():
    text = P.render_prompt("rectilinear_crossing", CROSSING_INSTANCE)
    edges_json = json.dumps(CROSSING_INSTANCE["edges"], separators=(",", ":"))
    assert edges_json in text


def test_crossing_prompt_names_every_required_certificate_field():
    text = P.render_prompt("rectilinear_crossing", CROSSING_INSTANCE)
    for field in ('"n"', '"edges"', '"coords"', '"crossings"'):
        assert field in text, field


def test_crossing_prompt_instructs_edges_must_be_unchanged():
    text = P.render_prompt("rectilinear_crossing", CROSSING_INSTANCE)
    assert "unchanged" in text


def test_crossing_prompt_forbids_extra_prose():
    text = P.render_prompt("rectilinear_crossing", CROSSING_INSTANCE)
    assert "NOTHING else" in text
    assert "JSON only" in text


# --- both families are covered, no silent third ------------------------------

def test_exactly_two_families_are_templated():
    assert set(P.TEMPLATES) == {"zarankiewicz", "rectilinear_crossing"}
