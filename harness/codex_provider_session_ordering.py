"""Ordered inbound merge for Codex provider-session events."""
from __future__ import annotations


class _InboundOrdering:
    def __init__(self):
        self.server_request = None
        self.notification = None

    def next(self, transport, *, wait_s: float = 0.0):
        self._fill(transport)
        if self.server_request is None and self.notification is None and wait_s:
            self.notification = transport.pop_notification(timeout=wait_s)
            if self.server_request is None:
                self.server_request = transport.pop_server_request(timeout=0.0)
        return self._choose()

    def _fill(self, transport) -> None:
        if self.server_request is None:
            self.server_request = transport.pop_server_request(timeout=0.0)
        if self.notification is None:
            self.notification = transport.pop_notification(timeout=0.0)

    def _choose(self):
        if self.server_request is None and self.notification is None:
            return None, None
        request_sequence = _sequence(self.server_request)
        note_sequence = _sequence(self.notification)
        if self.server_request is not None and request_sequence is None:
            return "missing_sequence", None
        if self.notification is not None and note_sequence is None:
            return "missing_sequence", None
        if self.server_request is None:
            return "notification", self._pop_notification()
        if self.notification is None:
            return "server_request", self._pop_server_request()
        if request_sequence == note_sequence:
            return "ambiguous_sequence", None
        if request_sequence < note_sequence:
            return "server_request", self._pop_server_request()
        return "notification", self._pop_notification()

    def _pop_server_request(self):
        value, self.server_request = self.server_request, None
        return value

    def _pop_notification(self):
        value, self.notification = self.notification, None
        return value


def _sequence(value) -> int | None:
    if value is None:
        return None
    sequence = getattr(value, "sequence", None)
    if isinstance(sequence, bool) or not isinstance(sequence, int):
        return None
    return sequence
