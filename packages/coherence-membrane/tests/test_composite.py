"""Tests for multimodal composition -- CompositeObservation + compare_composite."""

from __future__ import annotations

from coherence_membrane.composite import (
    CompositeObservation,
    compare_composite,
    composite_identity,
    perceive_composite,
)
from coherence_membrane.observation import Observation, Provenance, Status


def _obs(organ, subject, identity, fp=None, fp_key="perceptual_hash"):
    data = {"identity_sha256": identity}
    if fp is not None:
        data[fp_key] = fp
    return Observation(organ, subject, "observed", Status.PASS,
                       Provenance.witness_bytes(subject, b"x", "high"), data)


def _frame(identity, fp="00ff00ff00ff00ff"):
    return _obs("visual-artifact", "frame.png", identity, fp)


def _audio(identity, fp="0f0f0f0f0f0f0f0f"):
    return _obs("audio-artifact", "clip.wav", identity, fp, fp_key="perceptual_audio_hash")


def test_composite_identity_is_order_independent():
    a = _frame("a" * 64)
    b = _audio("b" * 64)
    assert composite_identity([a, b]) == composite_identity([b, a])


def test_composite_identity_changes_with_a_component():
    base = [_frame("a" * 64), _audio("b" * 64)]
    changed = [_frame("c" * 64), _audio("b" * 64)]
    assert composite_identity(base) != composite_identity(changed)


def test_compare_composite_match():
    base = CompositeObservation([_frame("a" * 64), _audio("b" * 64)])
    cur = CompositeObservation([_frame("a" * 64), _audio("b" * 64)])
    r = compare_composite(base, cur)
    assert r.verdict == "MATCH"
    assert all(c.verdict == "MATCH" for c in r.components)


def test_compare_composite_drift_in_one_modality():
    base = CompositeObservation([_frame("a" * 64, "0000000000000000"), _audio("b" * 64)])
    cur = CompositeObservation([_frame("d" * 64, "000000000000000f"), _audio("b" * 64)])  # frame changed
    r = compare_composite(base, cur)
    assert r.verdict == "DRIFT"
    by = {c.organ: c for c in r.components}
    assert by["visual-artifact"].verdict == "DRIFT" and by["visual-artifact"].distance == 4
    assert by["audio-artifact"].verdict == "MATCH"


def test_compare_composite_missing_modality_is_unverifiable():
    base = CompositeObservation([_frame("a" * 64), _audio("b" * 64)])
    cur = CompositeObservation([_frame("a" * 64)])  # audio went missing
    r = compare_composite(base, cur)
    assert r.verdict == "UNVERIFIABLE"
    by = {c.organ: c for c in r.components}
    assert by["audio-artifact"].verdict == "UNVERIFIABLE"


def test_drift_dominates_unverifiable():
    # one modality drifted AND another is missing -> overall DRIFT (the strongest signal)
    base = CompositeObservation([_frame("a" * 64, "0000000000000000"), _audio("b" * 64)])
    cur = CompositeObservation([_frame("d" * 64, "ffffffffffffffff")])  # frame drifted, audio missing
    r = compare_composite(base, cur)
    assert r.verdict == "DRIFT"


def test_empty_baseline_is_unverifiable():
    r = compare_composite(CompositeObservation([]), CompositeObservation([_frame("a" * 64)]))
    assert r.verdict == "UNVERIFIABLE"


def test_perceive_composite_runs_each_organ(make_png):
    from coherence_membrane.organs.visual import VisualArtifactOrgan

    png = make_png(4, 4, bytes(4 * 4 * 3))
    comp = perceive_composite([(VisualArtifactOrgan(), png)],
                              timestamp="2026-01-01T00:00:00+00:00")
    assert comp.timestamp == "2026-01-01T00:00:00+00:00"
    assert len(comp.components) == 1
    assert comp.by_organ("visual-artifact")
    assert len(comp.identity) == 64


def test_duplicate_key_in_current_is_order_independent_unverifiable():
    # two components with the same (organ, subject) in current is ambiguous; the
    # verdict must NOT depend on which one comes first (no last-write-wins).
    base = CompositeObservation([_frame("a" * 64, "0000000000000000")])
    drifted = _frame("d" * 64, "ffffffffffffffff")
    matching = _frame("a" * 64, "0000000000000000")
    r1 = compare_composite(base, CompositeObservation([matching, drifted]))
    r2 = compare_composite(base, CompositeObservation([drifted, matching]))
    assert r1.verdict == "UNVERIFIABLE" and r2.verdict == "UNVERIFIABLE"


def test_extra_modality_in_current_is_not_a_silent_match():
    base = CompositeObservation([_frame("a" * 64)])
    cur = CompositeObservation([_frame("a" * 64), _audio("b" * 64)])  # audio appeared
    r = compare_composite(base, cur)
    assert r.verdict == "UNVERIFIABLE"
    assert any(c.organ == "audio-artifact" for c in r.components)  # the extra is reported


def test_composite_identity_is_stable_after_caller_mutation():
    comps = [_frame("a" * 64), _audio("b" * 64)]
    comp = CompositeObservation(comps)
    ident = comp.identity
    comps.append(_frame("c" * 64))                  # mutate the caller's list
    comps[0].data["identity_sha256"] = "z" * 64     # mutate a caller component's data
    assert comp.identity == ident                    # snapshot isolates the witnessed instant


def test_int_fingerprint_is_accepted():
    base = CompositeObservation([_obs("visual-artifact", "f.png", "a" * 64, 255)])  # fp as int
    cur = CompositeObservation([_obs("visual-artifact", "f.png", "b" * 64, 0)])     # fp int 0
    by = {c.organ: c for c in compare_composite(base, cur).components}
    assert by["visual-artifact"].verdict == "DRIFT"
    assert by["visual-artifact"].distance == 8  # hamming(0xff, 0x00) == 8


def test_composite_roundtrips_through_dict():
    comp = CompositeObservation([_frame("a" * 64), _audio("b" * 64)], timestamp="t")
    back = CompositeObservation.from_dict(comp.to_dict())
    assert back.identity == comp.identity
    assert len(back.components) == 2
    assert compare_composite(comp, back).verdict == "MATCH"
