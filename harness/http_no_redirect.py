"""http_no_redirect.py -- open a request that carries a credential; follow no redirect.

`urllib.request.urlopen` follows 301, 302, 303, 307 and 308 and re-sends the
request's headers to the new host, a provider key in `Authorization` or
`x-api-key` among them. Every client in the harness that sends a credential
opens its request here (the provider transports go through
`endpoints_http.send`, which adds the gateway's accounting rule). A redirect
then comes back as the `HTTPError` it is, and the credential reaches only the
host it was configured for.

tests/test_gateway_provider_reach_inventory.py fails when a module calls
`urlopen` directly and is not on its list of clients that send no credential.
"""
from __future__ import annotations

import urllib.request

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                     # the 3xx comes back as the answer


_OPENER = urllib.request.build_opener(NoRedirect)


def open_request(req, timeout):
    """Open `req` and follow no redirect. A test that replaced
    `urllib.request.urlopen` still gets its replacement: a function that is not
    the standard library's own, whenever this module was first imported."""
    if getattr(urllib.request.urlopen, "__module__", "") != "urllib.request":
        return urllib.request.urlopen(req, timeout=timeout)
    return _OPENER.open(req, timeout=timeout)
