from articulate import detector, receipt

TEXT = "In today's landscape, we leverage cutting-edge synergy to unlock value.\n"


def test_fingerprint_is_deterministic():
    assert detector.ruleset_fingerprint() == detector.ruleset_fingerprint()
    assert detector.ruleset_fingerprint().startswith("sha256:")


def test_fingerprint_tracks_profile_changes(monkeypatch):
    # A receipt re-derives by loading its profile, so a profile edit is a ruleset
    # change. Editing a profile must move the fingerprint, so an old receipt reads
    # Unverifiable rather than a misleading Drift.
    from articulate import profiles
    fp0 = detector.ruleset_fingerprint()
    changed = dict(profiles.PROFILES)
    changed["research"] = {**changed["research"],
                           "keep": changed["research"]["keep"] + ("zzz-sentinel",)}
    monkeypatch.setattr(profiles, "PROFILES", changed)
    assert detector.ruleset_fingerprint() != fp0


def test_fingerprint_tracks_mode_changes(monkeypatch):
    # A mode's gate_promote drives check_text's gate, so a mode edit is a ruleset
    # change and must move the fingerprint too, before a receipt can name a mode.
    from articulate import modes
    fp0 = detector.ruleset_fingerprint()
    changed = dict(modes.MODES)
    changed["marketing/explain"] = {**changed["marketing/explain"], "gate_promote": ()}
    monkeypatch.setattr(modes, "MODES", changed)
    assert detector.ruleset_fingerprint() != fp0


def test_replay_same_text_is_match():
    rec = receipt.make_receipt(TEXT, "research")
    verdict, _ = receipt.verify_receipt(rec, TEXT)
    assert verdict == "Match"


def test_replay_different_text_is_unverifiable():
    rec = receipt.make_receipt(TEXT, "research")
    verdict, _ = receipt.verify_receipt(rec, "different clean prose.\n")
    assert verdict == "Unverifiable"


def test_tampered_receipt_is_drift():
    rec = receipt.make_receipt(TEXT, "research")
    assert rec["findings"], "TEXT must produce findings to tamper"
    rec["findings"][0]["rule_id"] = "tampered/rule"
    verdict, _ = receipt.verify_receipt(rec, TEXT)
    assert verdict == "Drift"


def test_stale_ruleset_is_unverifiable():
    rec = receipt.make_receipt(TEXT, "research")
    rec["ruleset_version"] = "sha256:0000000000000000"
    verdict, _ = receipt.verify_receipt(rec, TEXT)
    assert verdict == "Unverifiable"


def test_no_authority_verdict_exists():
    # The lattice is closed: there is no Trusted/Approved/Safe value.
    rec = receipt.make_receipt(TEXT, "research")
    verdict, _ = receipt.verify_receipt(rec, TEXT)
    assert verdict in {"Match", "Drift", "Unverifiable"}
