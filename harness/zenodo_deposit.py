"""zenodo_deposit.py -- deposit an artifact to Zenodo for a durable, citable DOI.

The durability dual anchor named in `anchor.py`. The Bitcoin leg answers "before
when"; this leg answers "and the bytes are still here, at a name anyone can cite".
Zenodo (run by CERN) mints a permanent DOI over the deposited bytes and preserves
them.

One digest binds the two anchors. The file deposited here is the same bytes whose
sha256 the Bitcoin timestamp covers, so a stranger checks that the file behind the
DOI hashes to the anchor digest and that that digest is the one the OpenTimestamps
proof starts from. Two independent witnesses, one digest, no shared trust root.

Publishing is irreversible: a published DOI cannot be unpublished or deleted. So
the flow stops before publish by default. `publish=True` is the one switch that
mints a permanent public record, and it is the caller's explicit choice.

The network is injected. Every network function takes a `request` callable so the
whole sequence is exercised by a fake transport in tests, never a live call. The
real transport is `urllib_transport`, standard-library only, with Bearer auth in a
header and never in a URL.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

_AGENT = "flywheel-anchor/1"


class DepositError(RuntimeError):
    """A deposit step could not be completed or returned an unexpected status."""


def api_base(*, sandbox: bool) -> str:
    """The API root. Sandbox and production are separate services with separate
    tokens and separate DOIs; a sandbox DOI is a throwaway, so the two must never
    be confused."""
    return "https://sandbox.zenodo.org/api" if sandbox else "https://zenodo.org/api"


def build_metadata(*, title: str, description: str, creators: list,
                   upload_type: str = "dataset", access_right: str = "open",
                   license: str = "cc-by-4.0", extra: dict = None) -> dict:
    """Assemble the `{"metadata": {...}}` body Zenodo's PUT expects.

    Required fields are checked here so a deposit never gets as far as the network
    with a body Zenodo will reject. An open deposit carries a license; that is
    Zenodo's rule, and encoding it here keeps the caller from a late 400.
    """
    if not title:
        raise DepositError("metadata needs a title")
    if not creators:
        raise DepositError("metadata needs at least one creator")
    md = {
        "title": title,
        "upload_type": upload_type,
        "description": description,
        "creators": [dict(c) for c in creators],
        "access_right": access_right,
    }
    if access_right == "open":
        md["license"] = license
    if extra:
        md.update(extra)
    return {"metadata": md}


def _headers(token: str, content_type: str) -> dict:
    """Bearer auth in a header, always. The token never reaches a URL."""
    return {"Authorization": f"Bearer {token}", "Content-Type": content_type,
            "User-Agent": _AGENT}


def _snippet(body: bytes) -> str:
    """First 200 bytes of a reply, for a debuggable error. The token never rides
    a response body, so this cannot leak the credential."""
    return bytes(body or b"")[:200].decode("utf-8", "replace")


def _parse(status: int, body: bytes, *, ok: set, ctx: str) -> dict:
    """Turn a (status, body) reply into JSON, or a named DepositError.

    Every failure a leg can meet leaves through DepositError: a wrong status, and
    a body that is accepted but is not the JSON the API contract promises.
    """
    if status not in ok:
        raise DepositError(f"{ctx}: HTTP {status} {_snippet(body)}".rstrip())
    if not body:
        return {}
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        raise DepositError(
            f"{ctx}: non-JSON body (HTTP {status}) {_snippet(body)}".rstrip())


def create(request, *, token: str, sandbox: bool = False) -> dict:
    """Open a new empty deposition; the reply carries the links the rest uses."""
    url = api_base(sandbox=sandbox) + "/deposit/depositions"
    status, body = request("POST", url,
                           headers=_headers(token, "application/json"), body=b"{}")
    return _parse(status, body, ok={200, 201}, ctx="create deposition")


def upload_file(request, *, token: str, bucket_url: str, name: str,
                data: bytes) -> dict:
    """PUT the raw file bytes to the deposition's bucket under `name`."""
    url = bucket_url.rstrip("/") + "/" + name
    status, body = request("PUT", url,
                           headers=_headers(token, "application/octet-stream"),
                           body=bytes(data))
    return _parse(status, body, ok={200, 201}, ctx=f"upload {name}")


def set_metadata(request, *, token: str, deposition_url: str,
                 metadata: dict) -> dict:
    """PUT the metadata wrapper (the `build_metadata` output) onto the deposition."""
    status, body = request("PUT", deposition_url,
                           headers=_headers(token, "application/json"),
                           body=json.dumps(metadata).encode())
    return _parse(status, body, ok={200}, ctx="set metadata")


def publish(request, *, token: str, publish_url: str) -> dict:
    """POST the publish action. Irreversible: the returned DOI is permanent."""
    status, body = request("POST", publish_url,
                           headers=_headers(token, "application/json"), body=b"")
    return _parse(status, body, ok={200, 202}, ctx="publish")


# Alias so the orchestrator can call the function without its `publish` boolean
# parameter shadowing this name in local scope.
_publish_action = publish


def deposit(request, *, token: str, files: list, metadata: dict,
            sandbox: bool = False, publish: bool = False) -> dict:
    """Run the full deposit: create, upload each file, set metadata, then stop.

    The default stops before publish. A deposition that is created but not
    published stays a private draft the operator can inspect, edit, or discard.
    Only `publish=True` mints the permanent public DOI, and it is reached exactly
    once, after every earlier step succeeded.
    """
    if not files:
        raise DepositError("deposit needs at least one file")
    record = create(request, token=token, sandbox=sandbox)
    links = record.get("links") or {}
    bucket = links.get("bucket")
    self_url = links.get("self")
    if not bucket or not self_url:
        raise DepositError("create reply missing bucket or self link")
    uploaded = [upload_file(request, token=token, bucket_url=bucket, name=name,
                            data=data) for name, data in files]
    set_metadata(request, token=token, deposition_url=self_url, metadata=metadata)
    result = {
        "deposition_id": record.get("id"),
        "self_url": self_url,
        "files": [f.get("key") for f in uploaded],
        "published": False,
        "doi": None,
        "doi_url": None,
        "does_not_prove": does_not_prove(),
    }
    if publish:
        publish_url = links.get("publish")
        if not publish_url:
            raise DepositError("create reply missing publish link")
        pub = _publish_action(request, token=token, publish_url=publish_url)
        result["published"] = True
        result["doi"] = pub.get("doi")
        result["doi_url"] = (pub.get("doi_url")
                             or (pub.get("links") or {}).get("doi"))
        result["record"] = pub
    return result


def urllib_transport(method: str, url: str, *, headers: dict = None,
                     body: bytes = None, timeout: float = 30.0):
    """The real network leg: stdlib urllib, returning (status, body_bytes).

    A 4xx/5xx is returned as its (status, body) rather than raised, so the one
    place that decides pass or fail is `_parse`. The Authorization header arrives
    from the caller; nothing here reads or logs it.
    """
    req = urllib.request.Request(url, data=None if body is None else bytes(body),
                                 method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise DepositError(f"{method} {url}: {e}")


def does_not_prove() -> list[str]:
    """What a DOI over the bytes still does not establish."""
    return [
        "NOT_PROVES_TIME: a DOI records that these bytes were deposited and are "
        "preserved, not when they first existed. Time is the Bitcoin leg's job; "
        "the DOI is durability and citability, not an ordering.",
        "NOT_PROVES_THE_BYTES_ARE_HONEST: Zenodo preserves and names whatever was "
        "uploaded. That the deposited head is truthful about the tree is the "
        "signature's and the verifier's concern, not the archive's.",
        "NOT_PROVES_EXCLUSIVE_AUTHORSHIP: anyone may deposit any bytes and receive "
        "a DOI. The DOI binds a name to bytes; it does not adjudicate who made "
        "them or whether an earlier deposit of the same bytes exists.",
    ]
