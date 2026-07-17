"""Routing receipts (landscape import 5): the failover decision leaves a
record — every candidate considered, its health verdict, the chosen
backend, and why — so routing is auditable and replayable instead of a
black box (Copilot Auto's gap)."""

from harness.local_agent import select_backend_receipted


class _B:
    def __init__(self, name, healthy):
        self.name = name
        self._healthy = healthy

    def health(self):
        return self._healthy


def test_the_decision_names_every_candidate_and_the_winner():
    backends = [_B("dead", False), _B("alive", True), _B("spare", True)]
    chosen, receipt = select_backend_receipted(backends)
    assert chosen.name == "alive"
    assert receipt["chosen"] == "alive"
    assert receipt["candidates"] == [
        {"name": "dead", "healthy": False},
        {"name": "alive", "healthy": True},
    ]  # probing stops at the first healthy one; unprobed spares not invented
    assert receipt["prefer"] == "auto"


def test_forcing_a_dead_backend_yields_an_honest_none():
    chosen, receipt = select_backend_receipted(
        [_B("a", True)], prefer="ghost")
    assert chosen is None
    assert receipt["chosen"] is None
    assert "no healthy backend" in receipt["note"]
