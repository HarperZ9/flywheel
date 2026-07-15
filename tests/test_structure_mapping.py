"""systematicity falsifier — relational preservation, the stricter transpile test.

Gentner/Bach: analogy preserves RELATIONS, not surface. So the conserving encoding
should preserve systematicity while the naive coarse encoding LOSES relations on
the pairs it collapses — and systematicity is a stricter test than locate error
(an encoding can decode "close enough" yet still flip an order relation).
"""
from harness.perception_probe import Scene, make_scene, conserving_encode, naive_encode, locate_error
from harness.structure_mapping import systematicity, relations, lost_relations


def test_conserving_preserves_relations():
    s = make_scene(7)
    assert systematicity(s, conserving_encode(s)) >= 0.95


def test_naive_loses_relations_on_collapsed_pairs():
    # alpha strictly left+above target, both inside ONE depth-1 cell (col D, row 4)
    # -> their order collapses to a tie under naive -> relations destroyed, kept
    # under the finer conserving encoding.
    s = Scene(w=512, h=288,
              objects=[("target", 122.0, 124.0), ("alpha", 100.0, 100.0),
                       ("beta", 400.0, 250.0)],
              target="target")
    sys_naive = systematicity(s, naive_encode(s))
    sys_cons = systematicity(s, conserving_encode(s))
    assert sys_cons > sys_naive, "the finer analogy must preserve more relational structure"
    # the destroyed relations are specifically the collapsed near-pair
    lost = lost_relations(s, naive_encode(s))
    assert any(set(l["pair"]) == {"alpha", "target"} for l in lost)


def test_systematicity_is_stricter_than_locate_error():
    # A collapsed near-pair: naive locate error stays BOUNDED (a few px) yet a
    # strict order relation is LOST -> surface-ok but structure-broken. This is the
    # whole point: relational fidelity is a stricter, reasoning-relevant test.
    s = Scene(w=512, h=288,
              objects=[("target", 122.0, 124.0), ("alpha", 100.0, 100.0)],
              target="target")
    naive = naive_encode(s)
    assert locate_error(s, naive) < 32       # surface error bounded (< one coarse cell)
    assert systematicity(s, naive) < 1.0     # but a relation is destroyed


def test_relations_are_well_formed():
    s = make_scene(3)
    r = relations(s)
    n = len(s.objects)
    assert len(r) == n * (n - 1) // 2        # one entry per unordered pair
    assert all(isinstance(v, tuple) and len(v) == 2 for v in r.values())


def test_undecodable_encoding_scores_zero_not_perfect():
    """Failed decodes must not collapse to a shared (-1,-1) point whose tie
    relations happen to MATCH true False relations: an encoding from which
    nothing decodes preserved nothing."""
    s = Scene(w=512, h=288,
              objects=[("b", 1.0, 1.0), ("a", 2.0, 2.0)],
              target="b")
    assert systematicity(s, "a: gibberish\nb: gibberish") == 0.0
