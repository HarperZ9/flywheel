"""Private export roots refuse to be redirected outside state custody.

Split out of test_journey_export_tx because these cases share one setup and
one question. Each of the four private roots (owner transaction directory,
staging, quarantine, target lock) is built by walking down from the state root
and creating what is missing. A link or a reparse point anywhere on that walk
would put transaction material somewhere the operator does not own, so the
walk refuses instead of resolving.
"""
import os
from pathlib import Path

import pytest

import harness.journey_export_tx as export_tx

OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _private_path(kind, state):
    value = {"owner_ref": OWNER, "client_request_sha256": "a" * 64,
             "packet_digest": "sha256:" + "b" * 64}
    if kind == "owner":
        return export_tx.owner_transaction_dir(state, OWNER)
    if kind == "staging":
        return export_tx.staging_path(state, value)
    if kind == "quarantine":
        return export_tx.quarantine_path(state, value)
    return export_tx.target_lock_path(state, "artifacts", "packets/out")


@pytest.mark.parametrize("kind", ("owner", "staging", "quarantine", "lock"))
def test_private_export_roots_reject_abstract_reparse_ancestor(
        tmp_path, monkeypatch, kind):
    """A Windows-style reparse ancestor must not redirect private custody."""
    state = tmp_path / "state"; suspect = state / "journey-exports"
    suspect.mkdir(parents=True)
    original = export_tx._is_reparse
    monkeypatch.setattr(export_tx, "_is_reparse", lambda path:
                        Path(path) == suspect or original(path))
    with pytest.raises(ValueError):
        _private_path(kind, state)
    assert not (suspect / "v2").exists()


@pytest.mark.skipif(os.name == "nt", reason="deterministic POSIX symlink case")
@pytest.mark.parametrize("kind", ("owner", "staging", "quarantine", "lock"))
def test_private_export_roots_reject_real_symlink_ancestor(tmp_path, kind):
    """A real symlink must not create transaction material outside state."""
    state, outside = tmp_path / "state", tmp_path / "outside"
    state.mkdir(); outside.mkdir()
    (state / "journey-exports").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        _private_path(kind, state)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("kind", ("owner", "staging", "quarantine", "lock"))
def test_private_export_roots_verify_state_containment(tmp_path, monkeypatch, kind):
    """Every private root must reject a computed path outside state custody."""
    state, outside = tmp_path / "state", tmp_path / "outside"
    state.mkdir(); outside.mkdir()
    monkeypatch.setattr(export_tx, "_tx_root", lambda _state: outside)
    with pytest.raises(ValueError):
        _private_path(kind, state)
    assert list(outside.iterdir()) == []
