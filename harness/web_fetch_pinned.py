"""A fetch that connects to the address it checked (7.2, N-28, SP-04).

The old path checked a host's addresses and then let urllib resolve it again,
a window in which a changing DNS answer could point the connection at a
private address; urllib also honored proxy variables. Here the host is
resolved once, every address must be global, and the connection goes to the
first checked address with the Host header and TLS server name set to the
hostname. `http.client` is used directly, so no proxy variable is consulted.
Userinfo is dropped from the request, and every redirect hop goes through the
same resolve-and-check. Proxy-dependent fetches therefore stop working.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.parse

MAX_REDIRECTS = 5
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


_SHARED = ipaddress.ip_network("100.64.0.0/10")  # CGNAT, and Tailscale tailnets


def is_global(address: str) -> bool:
    """Only globally routable unicast: private, loopback, link-local, shared
    (100.64.0.0/10, which tailnets use) and the rest are refused. An IPv4
    address mapped into IPv6 is judged as the IPv4 address."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.version == 4 and ip in _SHARED:
        return False
    return ip.is_global and not (ip.is_loopback or ip.is_private or ip.is_link_local
                                 or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, address: str, host: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        sock = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, address: str, host: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self):
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


def _target(url: str, resolver, allow_address):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"blocked: scheme {parts.scheme!r} or host is not allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    infos = resolver(parts.hostname, port, proto=socket.IPPROTO_TCP)
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise ValueError("blocked: host does not resolve")
    for address in addresses:
        if not allow_address(address):
            raise ValueError(f"blocked: {parts.hostname} resolves to {address}, which is "
                             "not a global address")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    default = port == (443 if parts.scheme == "https" else 80)
    host_header = parts.hostname if default else f"{parts.hostname}:{port}"
    return parts.scheme, parts.hostname, port, addresses[0], path, host_header


def fetch_pinned(url: str, *, resolver=socket.getaddrinfo, allow_address=is_global,
                 timeout: float = 60, max_bytes: int = 25_000_000):
    """(status, headers, body, final_url). Raises ValueError naming a block."""
    for _ in range(MAX_REDIRECTS + 1):
        scheme, host, port, address, path, host_header = _target(url, resolver, allow_address)
        kind = _PinnedHTTPS if scheme == "https" else _PinnedHTTP
        connection = kind(address, host, port, timeout)
        try:
            connection.request("GET", path, headers={"Host": host_header,
                                                     "User-Agent": USER_AGENT})
            response = connection.getresponse()
            location = response.getheader("Location")
            if 300 <= response.status < 400 and location:
                response.read(64 * 1024)
                url = urllib.parse.urljoin(url, location)
                continue
            return response.status, dict(response.getheaders()), \
                response.read(max_bytes + 1), url
        finally:
            connection.close()
    raise ValueError("blocked: too many redirects")
