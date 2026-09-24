"""Synthetic suites and arms for the decision bench tests.

Synthetic data only. A result on these suites says the harness behaves as
designed on them; it says nothing about any real family or model.
"""
import json
import random

FAMILY = "synthetic_relevance"
CRITERIA = {"true": "must be edited", "false": "can stay unchanged"}


def state_for(unit_id: str, words: int = 12) -> str:
    """A state whose every 8-word window is unique to its unit."""
    return "change " + " ".join(f"{unit_id}w{j}" for j in range(words))


def question(path: str, note: str) -> dict:
    return {"type": "noul", "criteria": dict(CRITERIA),
            "instructions": f"Does the change described in the state require "
                            f"editing {path} ({note})?"}


def make_items(split: str, n_units: int, *, per_unit: int = 4, seed: int = 1709) -> list:
    """Per unit: question 0 is the changed file (target true), the rest are
    unchanged (target false); one question per unit, drawn with the seed, is
    the certification question."""
    rng = random.Random(f"{seed}:{split}")
    items = []
    for n in range(n_units):
        unit = f"{split[:3]}{n:04d}"
        cert = rng.randrange(per_unit)
        for k in range(per_unit):
            items.append({
                "item_id": f"{unit}-q{k}", "unit_id": unit, "split": split,
                "state": state_for(unit),
                "question": question(f"pkg/{unit}/mod_{k}.py", f"helper {k}"),
                "target": "true" if k == 0 else "false", "tokens": 100 * (k + 1),
                "certification_unit": k == cert, "label_kind": "verified_outcome",
                "label_source_ref": f"synthetic:{unit}"})
    return items


def make_manifest(dev: int = 40, cal: int = 200, sealed: int = 200, **kw) -> dict:
    items = (make_items("development", dev, **kw) + make_items("calibration", cal, **kw)
             + make_items("sealed", sealed, **kw))
    return {"schema": "flywheel.decision-suite/v1", "family": FAMILY,
            "act_on": ["false"], "min_useful_coverage": 0.3,
            "build": {"synthetic": True}, "items": items}


def write_suite(tmp_path, manifest: dict | None = None):
    root = tmp_path / "suite"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest or make_manifest()), encoding="utf-8")
    return path


def write_card(manifest_path, arm: str, **fields) -> dict:
    """A hand-written policy card, standing in for decision_policy.fit_card."""
    import re
    card = {"status": "statistical_candidate_only", "threshold": 0.9,
            "temperature": 1.0, "temperature_applied": False, "max_error": 0.05,
            **fields}
    name = re.sub(r"[^A-Za-z0-9._-]", "_", arm)[:120]
    target = manifest_path.parent / "cards" / f"{name}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(card), encoding="utf-8")
    return card


class PathArm:
    """A label-blind arm that reads the synthetic path pattern: it answers
    true for ``mod_0`` and false otherwise, with a sure but not one-hot
    distribution. It stands in for a strong model arm."""

    backend_id = "fixture:path-arm"

    def capabilities(self) -> dict:
        return {"question_types": ["noul"], "max_options": 62,
                "max_state_tokens": None, "shared_state": True, "local": True,
                "deterministic": True, "sees_labels": False}

    def read(self, state, questions, *, deadline_ms=0) -> dict:
        answers = {}
        for qid, q in questions.items():
            p_true = 0.96 if "mod_0.py" in q["instructions"] else 0.02
            answers[qid] = {"raw": {"true": p_true, "false": 0.98 - p_true, "none": 0.02},
                            "label_mass": 0.97, "order_agreement": True}
        return {"answers": answers, "usage": {"input_tokens": 10, "output_tokens": 0},
                "reads": 2, "gpu_seconds": 0.01, "weights_sha256": None,
                "cache_path": "flat"}


def path_arm() -> PathArm:
    """Registry factory: ``module:tests.decision_bench_fixtures:path_arm``."""
    return PathArm()


PATH_ARM = "module:tests.decision_bench_fixtures:path_arm"
