"""Proof-surface packet validation, delegated to the shared contract package.

The proof-surface-packet schema is owned by the ``proof-surface`` package
(``proof_surface.packet``). This module is a thin adapter that keeps this
project's existing string-based API (``validate_proof_surface_packet`` ->
``list[str]``) while delegating the actual validation to that single source
of truth. Packet *construction*/emission lives in ``cli.py``; only the
duplicated validation logic was removed here.
"""

from __future__ import annotations

from typing import Any

from proof_surface.packet import validate_packet


def validate_proof_surface_packet(packet: dict[str, Any]) -> list[str]:
    """Validate a proof-surface packet, returning ``"path: message"`` strings.

    Returns an empty list when the packet is valid. Delegates to
    ``proof_surface.packet.validate_packet`` and renders each ``Issue`` into
    the flat string form this project's callers and tests expect.
    """
    return [f"{issue.path}: {issue.message}" for issue in validate_packet(packet)]
