"""sandbox_confinement.py -- the record a confined run leaves behind.

Split out of `posix_sandbox` so the builders and the record can each grow
without either one crowding the other out of a file.

One rule governs every field here: it may state what the kernel enforced and
nothing else. The row this serves has been corrected three times for breaking
it, once per field that promised more than the argv delivered, so the limits
are carried alongside the guarantees rather than left for a reader to supply
from the word sandbox.
"""
from __future__ import annotations

from dataclasses import dataclass

SCHEMA = "flywheel.posix-sandbox/v1"


@dataclass(frozen=True)
class Confinement:
    """Which backend ran, and what it actually enforced."""

    backend: str
    program: str
    root: str
    writable: tuple = ()
    network: bool = False
    reads_confined: bool = False
    processes_isolated: bool = False
    #: The credential paths hidden from this run. A denylist over an open
    #: filesystem, which is why it is counted separately from
    #: `reads_confined` rather than allowed to raise it.
    protected: tuple = ()
    #: The host rules a proxy was enforcing for this run, if one was. Empty
    #: means the network was open or denied outright, and `network` says
    #: which of those two it was.
    egress_hosts: tuple = ()
    egress_port: int | None = None

    def record(self) -> dict:
        return {"schema": SCHEMA, "backend": self.backend,
                "program": self.program, "root": self.root,
                "writable": list(self.writable), "network": self.network,
                "reads_confined": self.reads_confined,
                "processes_isolated": self.processes_isolated,
                "protected": [path for _, path in self.protected],
                "egress_hosts": list(self.egress_hosts),
                "egress_port": self.egress_port}

    def summary(self) -> str:
        """One line for the transcript, so a difference between hosts shows.

        The limits are named, not only the guarantee. A line that said
        confined and stopped there would let a reader supply the rest from
        the word, and the part they would supply is the part that is false.

        The scratch directory is counted rather than left out. It is
        writable and it is not under the workspace, so a line naming the
        workspace alone is short by one path. `writable` in the record has
        the paths themselves for a reader who wants them.

        Protected paths are counted and never described as read confinement.
        They are a denylist over an open filesystem, so the sentence stays
        `reads open` beside them and the two facts sit together where a
        reader cannot take one for the other.
        """
        extra = max(len(self.writable) - 1, 0)
        where = self.root if not extra else (
            f"{self.root} + {extra} scratch path"
            f"{'s' if extra > 1 else ''}")
        guard = (f", {len(self.protected)} path"
                 f"{'s' if len(self.protected) != 1 else ''} hidden"
                 if self.protected else "")
        return (f"[sandbox {self.backend}: writes confined to {where}, "
                f"reads {'confined' if self.reads_confined else 'open'}"
                f"{guard}, processes "
                f"{'isolated' if self.processes_isolated else 'shared'}, "
                f"network {self.network_words()}]")

    def network_words(self) -> str:
        """What the network was, in the three states it can be in.

        A run with a proxy is not an open network and it is not a denied
        one. Calling it either would be wrong in a direction a reader
        cannot recover from, so the middle state names the count of rules
        and `egress_hosts` in the record has the rules themselves.
        """
        if self.network:
            return "allowed"
        if not self.egress_hosts:
            return "denied"
        count = len(self.egress_hosts)
        return f"denied except {count} host rule{'s' if count > 1 else ''}"
