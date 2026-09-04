"""gateway_operation_infra.py -- the infrastructure-control actions.

The infra modules under `harness/infra/` were reachable only from their own
tests: a credential scanner, a boundary-isolation prober, and a kill switch
that no surface could ever reach. Each one either reads credential-shaped
material, leaves the machine, or tries to stop a running agent, so none of
them is a plain button. They are actions, and they arrive at the gateway the
same way every other action does, through a grant the operator approves once.

The field table lives here rather than in `gateway_operation.py` because that
module sits close to its size ceiling; the core merges these in so there is
still exactly one table at the point where anything reads it.
"""
from __future__ import annotations

_REFS = {"data_refs", "credential_refs"}

INFRA_FIELDS = {
    # Walks the environment and, when a root is named, the filesystem under
    # it, looking for credential-shaped text. It records a non-reversible
    # fingerprint and never the value, but it still reads the files where
    # secrets live, so the operator says yes before it starts.
    "infra.credential_scan": (set(_REFS), {"root"}),
    # Tries the paths an escaped agent would try: cloud metadata, a package
    # registry, DNS. Every one of them leaves the machine.
    "infra.isolation": (set(_REFS), set()),
    # The kill switch. Two named authorities, because one operator holding
    # both halves of a two-person rule is a one-person rule.
    "infra.kill": ({"reason", "authority_1", "authority_2"} | _REFS,
                   {"mode", "actions"}),
}

INFRA_PATHS = {
    "/api/infra/credential-scan": "infra.credential_scan",
    "/api/infra/isolation": "infra.isolation",
    "/api/infra/kill": "infra.kill",
}
