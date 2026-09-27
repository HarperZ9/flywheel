"""An export is never written to a network share, and the check opens nothing there.

Security review of 1.1.0, finding 2: the destination rule refused only the
``\\\\?\\`` and ``\\\\.\\`` device spellings. ``\\\\server\\share\\x`` and
``//server/share/x`` passed, after seven filesystem calls on the network path
(each one an SMB contact that can carry the owner's NTLM response, and a
name that falls back to broadcast resolution on the LAN), and the plaintext
copy was then written there. A mapped network drive went the same way.
"""
from __future__ import annotations

import os

import pytest

from harness import path_identity
from harness import trace_export_dest as dest

SHARES = ["\\\\fileserver.invalid\\share\\export1", "//fileserver.invalid/share/export2",
          "\\\\?\\UNC\\fileserver.invalid\\share\\x", "\\\\?\\C:\\x", "\\\\.\\PIPE\\x"]


def _networkish(value) -> bool:
    text = os.fspath(value).replace("/", "|").replace(chr(92), "|")
    return text.startswith("||") or "fileserver" in text


@pytest.fixture
def no_filesystem(monkeypatch):
    """Records any filesystem call on one of the network spellings, and
    answers it locally, so the test itself never contacts a share."""
    calls = []
    stand_in = {"lstat": FileNotFoundError, "stat": FileNotFoundError}

    def guard(name, original):
        def call(target, *args, **kwargs):
            if _networkish(target):
                calls.append((name, target))
                if name in stand_in:
                    raise stand_in[name](target)
                return False if name == "lexists" else target
            return original(target, *args, **kwargs)
        return call
    for name in ("lstat", "stat"):
        monkeypatch.setattr(dest.os, name, guard(name, getattr(os, name)))
    monkeypatch.setattr(dest.os.path, "lexists", guard("lexists", os.path.lexists))
    monkeypatch.setattr(dest.os.path, "realpath", guard("realpath", os.path.realpath))
    monkeypatch.setattr(path_identity, "_WINDOWS", True)
    return calls


@pytest.mark.parametrize("spelling", SHARES)
def test_a_network_or_device_destination_is_refused_with_no_filesystem_call(
        spelling, tmp_path, no_filesystem):
    with pytest.raises(dest.ExportError) as refused:
        dest.check(spelling, tmp_path / "home")
    assert refused.value.code in ("DESTINATION_NETWORK", "DESTINATION_DEVICE")
    assert no_filesystem == []


def test_a_mapped_network_drive_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(path_identity, "remote_drive", lambda _text, **_k: True)
    with pytest.raises(dest.ExportError) as refused:
        dest.check(str(tmp_path / "out"), tmp_path / "home")
    assert refused.value.code == "DESTINATION_NETWORK"


def test_a_grant_cannot_name_a_share(tmp_path, monkeypatch):
    monkeypatch.setattr(path_identity, "_WINDOWS", True)
    with pytest.raises(dest.ExportError) as refused:
        dest.create_grant(tmp_path / "home", "owner_" + "a" * 32, SHARES[0], {})
    assert refused.value.code == "DESTINATION_NETWORK"


def test_control_a_local_destination_passes(tmp_path):
    path, synced = dest.check(str(tmp_path / "out"), tmp_path / "home")
    assert path == tmp_path / "out" and synced is None
