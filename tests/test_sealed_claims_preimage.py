"""Every committed adjudication must carry the preimage of the seals it
displays: a stranger holding only the file re-derives every seal, and the
verdicts re-derive from the sealed thesis plus the stored measurements.
A seal without its preimage is decorative, not a receipt."""
import json
from pathlib import Path

import pytest

pytest.importorskip("crucible")

from crucible.assess import Assessment, recheck_assessment, verify_assessment
from crucible.claim import make_claim
from crucible.thesis import make_thesis

CLAIMS = Path(__file__).parent.parent / "docs" / "claims"


def _adjudications():
    return sorted(CLAIMS.glob("*/adjudication.json"))


def test_every_adjudication_carries_a_recomputable_preimage():
    paths = _adjudications()
    assert paths, "no adjudications on record"
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(doc.get("assessment"), dict), (
            f"{path}: displays seals without their preimage")
        a = Assessment.from_dict(doc["assessment"])
        assert verify_assessment(a), (
            f"{path}: the stored record does not re-derive its own seals")


@pytest.mark.parametrize("folder", ["2026-07-14-passk-forecast",
                                    "2026-07-14-k5-replication"])
def test_adjudication_rederives_from_its_sealed_thesis(folder):
    base = CLAIMS / folder
    tj = json.loads((base / "thesis.json").read_text(encoding="utf-8"))
    doc = json.loads((base / "adjudication.json").read_text(encoding="utf-8"))
    claims = [make_claim(c["text"], c.get("falsification", ""), id=c.get("id"))
              for c in tj["claims"]]
    thesis = make_thesis(tj["title"], claims, clock=lambda: 0.0)
    a = Assessment.from_dict(doc["assessment"])
    r = recheck_assessment(thesis, a)
    assert r["seals_ok"] and r["thesis_ok"] and r["verdicts_rederive"], (folder, r)
