"""typeface_family.py: one seed, a product line.

A family here is the same design DNA at several weights: the seed fixes
the skeleton micro-variation, so every instance shares its bones and
only the pen changes. Instances the legibility rules refuse are dropped
BY NAME, never silently, and the family receipt binds the seed, the
shared parameters, and every surviving instance's mint id into one
family id: a re-derivable product line, not a folder of files.
"""
from __future__ import annotations

import base64
import hashlib
import json

from .typeface_forge import DEFAULTS, mint
from .typeface_ttf import to_ttf

SCHEMA = "flywheel.typeface-family/v1"

# the default line: four weights that stay inside the counter rules
INSTANCES = (
    ("Light", 0.058),
    ("Regular", 0.085),
    ("Medium", 0.112),
    ("Bold", 0.145),
)


def mint_family(params: dict | None = None, seed: int = 58,
                family: str = "Zentropy Mint",
                instances: "list[tuple[str, float]] | None" = None) -> dict:
    """Mint every named weight from one seed; ship the survivors."""
    base = {**DEFAULTS, **(params or {})}
    base.pop("weight", None)
    rows = list(instances or INSTANCES)
    if not rows:
        return {"refused": True,
                "refusals": ["a family needs at least one named instance"]}

    shipped, refused = [], []
    for style, weight in rows:
        face = mint({**base, "weight": float(weight)}, seed=seed)
        if face["refused"]:
            refused.append({"style": str(style), "weight": float(weight),
                            "refusals": face["refusals"]})
            continue
        ttf = to_ttf(face, family=family, style=str(style))
        shipped.append({
            "style": str(style),
            "weight": float(weight),
            "mint_id": face["receipt"]["mint_id"],
            "ttf_sha256": hashlib.sha256(ttf).hexdigest(),
            "ttf_b64": base64.b64encode(ttf).decode("ascii"),
            "svg": face["svg"],
        })

    if not shipped:
        return {"refused": True,
                "refusals": ["every instance was refused: " + "; ".join(
                    r["refusals"][0] for r in refused)],
                "refused_instances": refused}

    family_doc = {
        "schema": SCHEMA,
        "family": family,
        "seed": int(seed),
        "params": {k: v for k, v in sorted(base.items())
                   if not k.startswith("_")},
        "instances": [{k: v for k, v in s.items()
                       if k in ("style", "weight", "mint_id", "ttf_sha256")}
                      for s in shipped],
        "refused_instances": refused,
    }
    family_doc["family_id"] = hashlib.sha256(
        json.dumps(family_doc, sort_keys=True).encode()).hexdigest()[:16]
    return {"refused": False, "refusals": [], "receipt": family_doc,
            "instances": shipped}
