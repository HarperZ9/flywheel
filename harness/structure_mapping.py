"""structure_mapping.py — systematicity: does a transpile preserve RELATIONS?

Gentner's structure-mapping theory (Bach 2012; Hofstadter, "Analogy as the Core
of Cognition") says analogical cognition preserves higher-order RELATIONAL
structure, not surface features — the *systematicity* principle. That is the
cognitive-science formalization of transpile-conservation: a faithful transform
conserves the relational criterion, not the bytes.

This sharpens the perception layer and explains its weak point. The perception
probe measured LOCATE error (a surface property: does the point decode close to
true?). Systematicity measures whether the RELATIONS between objects survive the
encoding (is A still left-of B? above B?). Structure-mapping predicts that
flexible reasoning needs relational preservation, not surface locatability — which
is exactly why the flexible-use marker came back COPY-ONLY (surface preserved,
relations not necessarily). Systematicity is the STRICTER, reasoning-relevant test.

Composes with perception_probe (Scene, encodings, decode_locate).
"""
from __future__ import annotations

from .perception_probe import Scene, decode_locate


def _pair_relations(objs: list[tuple[str, float, float]]) -> dict[tuple[str, str], tuple[bool, bool]]:
    """For each unordered name pair (a,b) with a<b lexically: (a_left_of_b,
    a_above_b) on the given coords. Ties (equal coord) count as False, so a
    collapse that makes two objects coincide DESTROYS their order relation."""
    coords = {nm: (x, y) for nm, x, y in objs}
    names = sorted(coords)
    rels = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ax, ay = coords[a]; bx, by = coords[b]
            rels[(a, b)] = (ax < bx, ay < by)
    return rels


def relations(scene: Scene) -> dict:
    return _pair_relations(scene.objects)


def decoded_relations(scene: Scene, encoding: str) -> dict:
    # an object that fails to decode is EXCLUDED: parking failures on a
    # shared placeholder point manufactured tie relations that scored an
    # undecodable encoding as perfectly systematic
    decoded = []
    for nm, _, _ in scene.objects:
        p = decode_locate(encoding, nm, scene.w, scene.h)
        if p is not None:
            decoded.append((nm, p[0], p[1]))
    return _pair_relations(decoded)


def systematicity(scene: Scene, encoding: str) -> float:
    """Fraction of (pair, predicate) relations preserved under the encoding. 1.0 =
    every left-of / above relation survives; lower = relational structure lost."""
    true_r = relations(scene)
    dec_r = decoded_relations(scene, encoding)
    total = preserved = 0
    for pair, (tl, ta) in true_r.items():
        dl, da = dec_r.get(pair, (None, None))
        total += 2
        preserved += int(dl == tl) + int(da == ta)
    return preserved / total if total else 1.0


def lost_relations(scene: Scene, encoding: str) -> list[dict]:
    """The specific relations the encoding destroyed — the structure-mapping
    diagnosis of WHERE faithfulness broke, not just that it did."""
    true_r = relations(scene)
    dec_r = decoded_relations(scene, encoding)
    out = []
    for pair, (tl, ta) in true_r.items():
        dl, da = dec_r.get(pair, (None, None))
        if dl != tl:
            out.append({"pair": pair, "relation": "left_of", "true": tl, "decoded": dl})
        if da != ta:
            out.append({"pair": pair, "relation": "above", "true": ta, "decoded": da})
    return out
