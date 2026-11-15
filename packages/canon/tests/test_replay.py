from __future__ import annotations

import pytest

from canon.replay import ReplayClaim, ReplayError, check_replay_claim, replay_key


def _sha(hex_char: str) -> str:
    return "sha256:" + hex_char * 64


def _claim(nonce: str = "n1", expires_ord: int = 10) -> ReplayClaim:
    return ReplayClaim(
        principal="operator",
        source_state_sha256=_sha("1"),
        capsule_sha256=_sha("2"),
        nonce=nonce,
        expires_ord=expires_ord,
    )


class _HostileReplayClaim(ReplayClaim):
    pass


def _claim_subclass() -> ReplayClaim:
    return _HostileReplayClaim(
        principal="operator",
        source_state_sha256=_sha("1"),
        capsule_sha256=_sha("2"),
        nonce="n1",
        expires_ord=10,
    )


def test_replay_key_is_stable_and_content_bound() -> None:
    claim = _claim()

    assert replay_key(claim) == (
        "sha256:1c0afcfb9937218455c4f57d55f04cfbaac20dcc8bde4f71c700fef2c56e4ad9"
    )
    assert replay_key(claim) == replay_key(_claim())
    assert replay_key(claim) != replay_key(_claim(nonce="n2"))
    assert "operator" not in replay_key(claim)


def test_duplicate_replay_claim_is_rejected() -> None:
    seen: set[str] = set()
    key = check_replay_claim(_claim(), seen=seen, current_ord=1)
    assert key in seen

    try:
        check_replay_claim(_claim(), seen=seen, current_ord=2)
    except ReplayError as exc:
        assert exc.code == "replay"
    else:
        raise AssertionError("expected ReplayError")


def test_expired_replay_claim_is_rejected() -> None:
    try:
        check_replay_claim(_claim(expires_ord=3), seen=set(), current_ord=3)
    except ReplayError as exc:
        assert exc.code == "stale"
    else:
        raise AssertionError("expected ReplayError")


def test_replay_accepts_claim_before_expiration_boundary() -> None:
    seen: set[str] = set()
    key = check_replay_claim(_claim(expires_ord=3), seen=seen, current_ord=2)

    assert seen == {key}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("principal", ""),
        ("principal", 123),
        ("principal", "operator\n"),
        ("source_state_sha256", "sha256:" + "A" * 64),
        ("source_state_sha256", "sha256:deadbeef"),
        ("capsule_sha256", "sha256:" + "A" * 64),
        ("capsule_sha256", 123),
        ("nonce", ""),
        ("nonce", "n\0x"),
        ("nonce", 123),
        ("expires_ord", 0),
        ("expires_ord", -1),
        ("expires_ord", True),
        ("expires_ord", "10"),
    ],
)
def test_replay_claim_rejects_invalid_field_shapes(
    field: str,
    value: object,
) -> None:
    data: dict[str, object] = {
        "principal": "operator",
        "source_state_sha256": _sha("1"),
        "capsule_sha256": _sha("2"),
        "nonce": "n1",
        "expires_ord": 10,
    }
    data[field] = value

    with pytest.raises(ReplayError, match="invalid-replay-claim"):
        ReplayClaim(**data)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("seen", "current_ord"),
    [
        ([], 1),
        ({"not-a-sha256-key"}, 1),
        (set(), True),
        (set(), -1),
    ],
)
def test_check_replay_claim_validates_inputs_before_mutating_seen(
    seen: object,
    current_ord: object,
) -> None:
    original = set(seen) if isinstance(seen, set) else None

    with pytest.raises(ReplayError):
        check_replay_claim(_claim(), seen=seen, current_ord=current_ord)  # type: ignore[arg-type]

    if original is not None:
        assert seen == original


def test_check_replay_claim_rejects_hostile_set_subclass() -> None:
    class HostileSeen(set[str]):
        def __contains__(self, value: object) -> bool:
            return False

        def add(self, value: str) -> None:
            return None

    seen = HostileSeen()

    with pytest.raises(ReplayError, match="invalid-seen"):
        check_replay_claim(_claim(), seen=seen, current_ord=1)  # type: ignore[arg-type]

    assert seen == set()


def test_stale_replay_claim_does_not_mark_claim_seen() -> None:
    seen: set[str] = set()

    with pytest.raises(ReplayError, match="stale"):
        check_replay_claim(_claim(expires_ord=3), seen=seen, current_ord=3)

    assert seen == set()


def test_replay_key_rejects_non_claim() -> None:
    with pytest.raises(ReplayError, match="invalid-replay-claim"):
        replay_key(object())  # type: ignore[arg-type]


def test_replay_key_rejects_replay_claim_subclass() -> None:
    with pytest.raises(ReplayError, match="invalid-replay-claim"):
        replay_key(_claim_subclass())


def test_replay_key_revalidates_mutated_claim_hash() -> None:
    claim = _claim()
    object.__setattr__(claim, "capsule_sha256", "sha256:" + "A" * 64)

    with pytest.raises(ReplayError, match="invalid-replay-claim"):
        replay_key(claim)


def test_check_replay_claim_revalidates_mutated_claim_before_seen_mutation() -> None:
    claim = _claim()
    seen: set[str] = set()
    object.__setattr__(claim, "expires_ord", True)

    with pytest.raises(ReplayError, match="invalid-replay-claim"):
        check_replay_claim(claim, seen=seen, current_ord=1)

    assert seen == set()


def test_check_replay_claim_rejects_claim_subclass_before_seen_mutation() -> None:
    seen: set[str] = set()

    with pytest.raises(ReplayError, match="invalid-replay-claim"):
        check_replay_claim(_claim_subclass(), seen=seen, current_ord=1)

    assert seen == set()
