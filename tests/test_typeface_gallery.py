"""The typeface marketplace: a published face is browsable, fetchable with
its bytes, idempotent to republish, re-derivable from the stored seed and
params, and a refused face is never a product."""

import base64

import pytest

from harness.typeface_forge import mint, DEFAULTS
from harness.typeface_ttf import to_ttf
from harness.typeface_gallery import publish_face, gallery, fetch_face, KIND


def _face(seed=201, weight=0.09):
    base = {k: v for k, v in DEFAULTS.items() if k != "weight"}
    f = mint({**base, "weight": weight}, seed=seed)
    f["ttf_b64"] = base64.b64encode(to_ttf(f)).decode("ascii")
    return f


def test_a_published_face_lists_with_metadata_and_fetches_with_bytes(tmp_path,
                                                                     monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    import importlib
    import harness.store as store
    importlib.reload(store)
    import harness.typeface_gallery as gal
    importlib.reload(gal)

    pub = gal.publish_face(_face(), family="Test Face")
    assert pub["published"] and pub["eid"].startswith("face-")
    listing = gal.gallery()
    assert listing["count"] == 1
    entry = listing["faces"][0]
    assert entry["mint_id"] == pub["mint_id"]
    assert "ttf_b64" not in entry            # the listing is metadata only
    full = gal.fetch_face(pub["eid"])
    assert full["ttf_b64"]                   # the bytes come on the fetch
    assert "weight" in full["params"]


def test_republishing_the_same_face_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    import importlib
    import harness.store as store
    importlib.reload(store)
    import harness.typeface_gallery as gal
    importlib.reload(gal)

    f = _face(seed=77)
    a = gal.publish_face(f)
    b = gal.publish_face(f)
    assert a["eid"] == b["eid"]              # keyed on mint_id, not attempt
    assert gal.gallery()["count"] == 1


def test_a_gallery_face_re_derives_from_its_stored_seed_and_params(tmp_path,
                                                                   monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    import importlib
    import harness.store as store
    importlib.reload(store)
    import harness.typeface_gallery as gal
    importlib.reload(gal)

    pub = gal.publish_face(_face(seed=303, weight=0.11))
    full = gal.fetch_face(pub["eid"])
    remint = mint({**full["params"]}, seed=full["seed"])
    assert remint["receipt"]["mint_id"] == full["mint_id"]


def test_a_refused_face_is_not_published():
    refused = {"refused": True, "refusals": ["counter too tight"], "receipt": {}}
    out = publish_face(refused)
    assert "error" in out and "refused" in out["error"]


def test_fetch_of_an_unknown_id_is_a_named_error():
    out = fetch_face("face-deadbeef")
    assert "error" in out
