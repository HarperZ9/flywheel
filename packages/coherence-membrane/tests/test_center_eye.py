"""The eye (a real VisualArtifactOrgan) wired as the center's PERCEIVE mind."""
from __future__ import annotations

from coherence_membrane.certificate import Verdict
from coherence_membrane.center import CriterionSpec, reconcile_at_center, winner_of, scores_of
from coherence_membrane.center.eye import EyeMind, EyeJudge, EYE_DIMS

_RGB = lambda step: bytes((i * step) % 256 for i in range(16 * 16 * 3))


def test_eye_perceives_a_real_image(make_png, tmp_path):
    p = tmp_path / "art.png"; p.write_bytes(make_png(16, 16, _RGB(7)))
    store = {}
    prop = EyeMind("eye", store=store).perceive_and_propose(str(p))
    assert "decoded=True" in prop and "phash=None" not in prop and "phash=" in prop
    obs = store[prop]
    assert obs.data.get("decoded") and obs.data.get("perceptual_hash")     # a REAL witnessed perception


def test_eye_judge_scores_real_perception(make_png, tmp_path):
    p = tmp_path / "art.png"; p.write_bytes(make_png(16, 16, _RGB(7)))
    store = {}
    prop = EyeMind("eye", store=store).perceive_and_propose(str(p))
    sc = EyeJudge(store).score(prop, {}, EYE_DIMS)
    assert sc["decoded"] == 1.0 and sc["confidence"] > 0.0
    # a candidate the eye never perceived scores 0 on every perceptual dim
    assert all(v == 0.0 for v in EyeJudge(store).score("plain text", {}, EYE_DIMS).values())


def test_eye_on_unreadable_is_honest():
    store = {}
    prop = EyeMind("eye", store=store).perceive_and_propose("no-such-artifact.png")
    assert EyeJudge(store).score(prop, {}, EYE_DIMS)["decoded"] == 0.0


def test_center_loop_with_two_eyes(make_png, tmp_path):
    pa = tmp_path / "a.png"; pa.write_bytes(make_png(16, 16, _RGB(7)))
    pb = tmp_path / "b.png"; pb.write_bytes(make_png(16, 16, _RGB(3)))
    store = {}
    minds = [EyeMind("eye-a", "percA", store=store), EyeMind("eye-b", "percB", store=store)]
    crit = CriterionSpec("clear-eye", {"perceived": 0.4, "decoded": 0.4, "confidence": 0.2})
    cert = reconcile_at_center({"percA": str(pa), "percB": str(pb)}, minds, crit, EyeJudge(store), dims=EYE_DIMS)
    assert cert.verdict is Verdict.VERIFIED and winner_of(cert) in scores_of(cert)
    # every candidate -- solo AND meeting -- is a real witnessed perception (decoded, scored)
    assert all(c.get("decoded", 0) > 0 for c in scores_of(cert).values())
