"""egress_policy.py -- which hosts a confined command may reach, and why.

The two POSIX backends have one network control between them and it is a
switch. `--unshare-net` gives bubblewrap a namespace with no route off the
machine, and `(deny network*)` gives a Seatbelt profile the same answer.
Turn either one off and the confined command has the whole internet. A build
that needs one package index has to be handed all of it, and the receipt
then records `network: true`, which is true and says almost nothing about
where the run could go.

This module is the policy half of a narrower answer: a named set of hosts
and ports, matched as text, with no wildcard able to widen itself. The
enforcement half is `egress_proxy`. Nothing here opens a socket, so what a
run was permitted to reach can be read in a diff.

Two limits are stated rather than left for a reader to supply.

A name list is not an address list. The proxy is told the name the client
asked for, so a client that asks for an address presents no name to match,
and `1.2.3.4` is reachable only when `1.2.3.4` is itself in the list.

A name that resolves is not a name that stays put. The list is checked
before resolution and the address is checked after it, because a name in the
list can answer with the loopback interface or a cloud metadata address, and
a policy that stopped at the name would carry the request to either.
"""
from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass

SCHEMA = "flywheel.egress-policy/v1"

#: The port a policy allows when the caller names none. One port, and the
#: one that carries a checkable certificate: a default that included 80
#: would hand every policy a cleartext route nobody asked for.
DEFAULT_PORTS = (443,)

#: Characters that cannot appear in a host pattern. Each one means the
#: caller wrote something other than a host and a matcher would quietly
#: agree with a different reading of it.
FORBIDDEN = (":", "/", "\\", "@", "?", "#", " ", "\t", "%", "[", "]")


class PolicyRefused(ValueError):
    """A pattern cannot be matched without widening what it appears to say."""


def _pattern(text) -> str:
    """One host pattern, folded to the form the matcher compares, or a
    refusal.

    Refusal rather than a best effort. A pattern this function could not
    read is one whose author had a reading in mind, and guessing which
    reading produces an allowlist that permits something nobody wrote down.
    """
    if not isinstance(text, str):
        raise PolicyRefused(f"host pattern is not text: {text!r}")
    clean = text.strip().rstrip(".").lower()
    if not clean:
        raise PolicyRefused("host pattern is empty")
    if clean == "*":
        raise PolicyRefused(
            "a policy allowing every host is not an allowlist: ask for an "
            "unrestricted run and let the record say that instead")
    for bad in FORBIDDEN:
        if bad in clean:
            raise PolicyRefused(f"host pattern holds {bad!r}: {text!r}")
    body = clean[2:] if clean.startswith("*.") else clean
    if not body or "*" in body:
        raise PolicyRefused(
            f"a wildcard is only a leading '*.' label: {text!r}")
    return clean


def _port(value) -> int:
    """One port number, or a refusal. Booleans are not ports."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolicyRefused(f"port is not an integer: {value!r}")
    if not 1 <= value <= 65535:
        raise PolicyRefused(f"port is outside 1-65535: {value}")
    return value


def _literal(host: str):
    """The address `host` already is, or None when it is a name."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


@dataclass(frozen=True)
class EgressPolicy:
    """The hosts and ports one confined run may reach.

    Every construction validates, so a policy that exists is a policy whose
    patterns were readable. An empty `hosts` is a real policy and it denies
    everything, which is the right answer for a run that named nothing.
    """

    hosts: tuple = ()
    ports: tuple = DEFAULT_PORTS

    def __post_init__(self):
        object.__setattr__(
            self, "hosts", tuple(_pattern(one) for one in self.hosts))
        object.__setattr__(
            self, "ports", tuple(_port(one) for one in self.ports))

    def allows(self, host, port) -> bool:
        """True when this exact host and port were named.

        Never raises. A malformed request is a denial, because this is
        consulted by a server reading bytes off a socket and an exception
        there is a way for a request to reach a code path nobody wrote a
        rule for.

        An address asked for by a client matches only itself. A `*.` pattern
        is a name rule, and letting `1.2.3.4` match `*.3.4` would turn one
        into an address rule by accident.
        """
        try:
            asked = _pattern(host)
            wanted = _port(port)
        except PolicyRefused:
            return False
        if asked.startswith("*.") or wanted not in self.ports:
            return False
        literal = _literal(asked)
        for pattern in self.hosts:
            if pattern == asked:
                return True
            if literal is None and pattern.startswith("*."):
                if asked.endswith(pattern[1:]):
                    return True
        return False

    def record(self) -> dict:
        return {"schema": SCHEMA, "hosts": list(self.hosts),
                "ports": list(self.ports)}

    def summary(self) -> str:
        """One line for the transcript, naming the policy rather than the
        guarantee."""
        if not self.hosts:
            return "[egress: no host allowed]"
        ports = ",".join(str(one) for one in self.ports)
        return (f"[egress: {len(self.hosts)} host rule"
                f"{'s' if len(self.hosts) > 1 else ''} on port {ports}]")


def _unwrap(addr):
    """The IPv4 address an IPv6 one carries, or the address itself.

    `::ffff:127.0.0.1` reaches the loopback interface and
    `IPv6Address.is_loopback` answers False about it, so a guard that asked
    the property directly would pass the address it exists to stop. 6to4 and
    Teredo carry an embedded address the same way. Whether a given Python
    version folds these into `is_private` has changed, so the unwrapping is
    done here rather than assumed of the library.
    """
    if getattr(addr, "version", 4) != 6:
        return addr
    for name in ("ipv4_mapped", "sixtofour", "teredo"):
        inner = getattr(addr, name, None)
        if isinstance(inner, tuple):
            inner = inner[1]
        if inner is not None:
            return inner
    return addr


def blocked_address(text) -> str | None:
    """Why this resolved address may not be connected to, or None.

    The name was checked against the list before anything was resolved.
    This is the check after it, and it is the one that stops a name in the
    list from carrying a request to the machine the sandbox is running on or
    to the metadata service of the cloud instance it is running in. Neither
    of those is reachable by name from the list, and both are reachable by a
    DNS answer that names them.

    Order matters only for the words. An IPv4 loopback address is private as
    well, and a reader chasing a denial is better served by "loopback" than
    by "private".
    """
    try:
        addr = _unwrap(ipaddress.ip_address(text))
    except ValueError:
        return "not an address"
    for reason, held in (("unspecified", addr.is_unspecified),
                         ("loopback", addr.is_loopback),
                         ("link-local", addr.is_link_local),
                         ("multicast", addr.is_multicast),
                         ("reserved", addr.is_reserved),
                         ("private", addr.is_private)):
        if held:
            return reason
    return None


#: Where an operator names the hosts a confined run may reach. Absent means
#: nobody asked for filtering, which is a different answer from a policy
#: naming no host.
ENV_HOSTS = "FLYWHEEL_EGRESS_HOSTS"

#: Ports, when the default of 443 alone is not what the run needs.
ENV_PORTS = "FLYWHEEL_EGRESS_PORTS"


def from_env(environ=None):
    """The policy this host configured, or None when it configured none.

    None and an empty policy are different answers and both are reachable.
    None means nobody asked for filtering, so the caller keeps whatever
    network behaviour it already had. A variable set to nothing is a policy
    naming no host, which denies everything, and an operator who wants a run
    with no network at all has a way to say so.

    A value that does not parse raises rather than falling back. Somebody
    typed a policy and a quiet default would run the command under a policy
    they did not write.
    """
    env = os.environ if environ is None else environ
    raw = env.get(ENV_HOSTS)
    if raw is None:
        return None
    hosts = tuple(one.strip() for one in raw.split(",") if one.strip())
    written = env.get(ENV_PORTS, "").strip()
    if not written:
        return EgressPolicy(hosts=hosts)
    ports = [one.strip() for one in written.split(",") if one.strip()]
    if not ports:
        raise PolicyRefused(f"{ENV_PORTS} names no port")
    # Only a run of digits becomes a number here. Anything else is handed to
    # the policy as it was written, so `_port` refuses it and there is one
    # place that decides what a port is.
    return EgressPolicy(
        hosts=hosts,
        ports=tuple(int(one) if one.isdigit() else one for one in ports))
