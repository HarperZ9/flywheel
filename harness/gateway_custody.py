"""Which gateway routes sit under private custody, in one place.

The auth check refuses these without a configured bearer token, and the
generated API document marks them as needing one. Those are two readers of
the same fact, and when the fact lived inline in the auth check the document
had to restate it, which is how a document ends up telling a caller a route is
open that the gateway refuses. Both read this module now.

Its own file rather than a few lines in `harness/gateway.py` because the
document builder should not have to import a 2,300-line HTTP handler to ask
one question about a path.
"""

from __future__ import annotations

#: Everything under these prefixes is private, however deep.
PRIVATE_PREFIXES = ("/api/journeys/", "/api/grants/", "/api/plan/",
                    "/api/auth/",
                    "/api/continuation/",
                    "/api/writing/",
                    "/api/gateway-grants/", "/api/pm/",
                    "/api/enterprise-envs/",
                    "/api/lane/",
                    "/api/credential-handles", "/api/session-tokens",
                    "/api/bulletin-identity", "/api/operations/", "/api/hooks/")

#: Exact paths held under private custody. Model calls and anything that runs
#: an agent, installs a plugin, or reaches the marketplace.
PRIVATE_PATHS = frozenset({
    "/api/auth", "/api/agent/run", "/api/agent/runs",
    "/v1/chat/completions", "/api/agent", "/api/output/check", "/api/workflow",
    "/api/hooks", "/api/operations",
    "/api/plugins/probe", "/api/plugins/call", "/api/plugins/register",
    "/api/plugins/toggle", "/api/plugins/remove",
    "/api/marketplace/install", "/api/marketplace/add",
    "/api/marketplace/remove",
    # Minting a runner enrollment ticket is the one act in the pool that
    # decides who may join it. The machines' own routes stay open, because
    # a runner has to reach them; this one is the operator's.
    "/api/runners/tickets"})


def is_private(path: str) -> bool:
    """Does this path sit under private custody? One rule, two readers."""
    return path.startswith(PRIVATE_PREFIXES) or path in PRIVATE_PATHS
