"""`flywheel monitor owner` prints the installed rule-pack digest, for re-pinning.

Success criteria:
- the printed installed_rules_digest equals pack_digest(load_pack()) of the
  shipped pack;
- it is the shipped pack's digest, not the owner file's digest, so the two
  fields can be told apart (control: they differ).
"""
from __future__ import annotations

import io
import json

from harness.preaction.cli import main
from harness.preaction.rules import load_pack, pack_digest


def test_owner_prints_the_installed_rules_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path))
    out = io.StringIO()
    assert main(["owner"], stdout=out) == 0
    doc = json.loads(out.getvalue())
    assert doc["installed_rules_digest"] == pack_digest(load_pack())
    assert doc["installed_rules_digest"] != doc["digest"]
