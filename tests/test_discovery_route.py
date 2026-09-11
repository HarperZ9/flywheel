"""The gateway's machine-discovery surface, and the parse it is built on.

Three documents tell a caller what this gateway serves. The risk they carry is
not that they are wrong today, it is that they are right today and quietly
wrong in a month, which is what happens to every API document somebody
maintains by hand. So the tests here are mostly about the mechanism: a route
added to the gateway has to reach the document without anyone touching the
document, and a route nobody described has to fail rather than ship blank.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from harness import discovery_route as disc  # noqa: E402
from harness.gateway_custody import is_private  # noqa: E402
from harness.route_inventory import (EXACT, PREFIX, gateway_routes,  # noqa: E402
                                     routes_in, undescribed)
from harness.writing_operations import http_operations  # noqa: E402
from harness.writing_route import writing_get, writing_post  # noqa: E402

NOW = "2026-09-10T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

SYNTHETIC = '''
class _Handler:
    def _get(self):
        p = self.path
        if p == "/api/newly-added":                # what this new route answers
            return self._json({})
        if p.startswith("/api/newly-added/"):
            return self._json({})
    def _post(self):
        p = self.path
        if p == "/api/newly-added":                # and what posting to it does
            return self._json({})
'''


def test_a_route_added_to_the_gateway_reaches_the_document_untouched():
    """The whole point of parsing instead of maintaining.

    Nobody edits a list when a route is added. If this ever fails, the
    document has quietly become hand-maintained and everything else here is
    checking a copy rather than the code.
    """
    found = {r.path: r for r in routes_in(SYNTHETIC)}
    assert set(found) == {"/api/newly-added", "/api/newly-added/"}
    exact = found["/api/newly-added"]
    assert exact.match == EXACT
    assert exact.methods == ("GET", "POST"), "reached by two dispatchers"
    assert exact.description == "what this new route answers"
    assert found["/api/newly-added/"].match == PREFIX


def test_a_route_nobody_described_is_named_rather_than_counted():
    """The falsifier for the description gate below.

    A gate that cannot fail is decoration, so the undescribed route in this
    synthetic source has to come back by name.
    """
    assert undescribed(routes_in(SYNTHETIC)) == ["/api/newly-added/"]


def test_every_route_the_gateway_dispatches_on_is_described():
    """The gate. A blank summary in a published document is worse than none,
    because a reader takes it for a route with nothing to say."""
    missing = undescribed()
    assert not missing, (
        "these gateway routes have no trailing # comment on their dispatch "
        f"line, so the API document would ship them blank: {missing}")


def test_the_document_never_claims_a_route_the_code_does_not_dispatch():
    """An upper bound is the dangerous direction.

    A document missing a route costs a caller a question. A document naming a
    route that does not exist costs them a debugging session against a 404
    they were told to expect.
    """
    served = {r.path for r in gateway_routes()}
    descriptor_backed = {op.http_path for op in http_operations()}
    for path in disc.openapi_document()["paths"]:
        real = path.removesuffix("{subpath}")
        assert real in served or real in descriptor_backed, path


def test_descriptor_backed_writing_paths_reach_the_route_adapter(tmp_path):
    """A Writing descriptor path only belongs in OpenAPI if the adapter knows it.

    Incomplete requests are enough for this guard: a known route returns a
    field/type error or a successful read, while an unhandled descriptor falls
    through as NOT_FOUND.
    """
    for op in http_operations():
        if op.http_method == "GET":
            body, _status = writing_get(op.http_path, owner_ref=OWNER,
                state_root=tmp_path / "state", clock=lambda: NOW)
        else:
            body, _status = writing_post(op.http_path, b"{}",
                owner_ref=OWNER, state_root=tmp_path / "state",
                clock=lambda: NOW)
        assert body.get("error", {}).get("code") != "NOT_FOUND", op.http_path


def test_private_custody_is_read_from_the_gateway_rule_not_restated():
    """One rule, two readers.

    If the document decided custody on its own, it could mark a route open
    that the auth check refuses, and a caller would read the document, send
    no token, and get a refusal the document said would not come.
    """
    marked, refused = set(), set()
    for path, entry in disc.openapi_document()["paths"].items():
        real = path.removesuffix("{subpath}")
        if any(isinstance(op, dict) and op.get("x-flywheel-custody") == "private"
               for op in entry.values()):
            marked.add(real)
        if is_private(real):
            refused.add(real)
    assert marked == refused
    assert "/api/agent" in marked, "a known private route lost its marker"
    assert "/api/world" not in marked, "a read-only route was marked private"


def test_each_document_carries_the_lower_bound_it_is_built_on():
    """The limit travels with the claim, in all three shapes.

    The parse cannot see a path assembled at runtime. Saying so once in a
    source file the reader never opens is not saying it.
    """
    assert disc.LOWER_BOUND in disc.openapi_document()["info"]["description"]
    assert disc.LOWER_BOUND in disc.llms_txt()
    assert disc.LOWER_BOUND in disc.card()["note"]
    assert "parsed gateway dispatchers plus descriptor-backed Writing" in (
        disc.LOWER_BOUND)


def test_the_discovery_paths_appear_in_their_own_documents():
    """A document that omits itself teaches a caller the wrong entry point."""
    paths = disc.openapi_document()["paths"]
    text = disc.llms_txt()
    for path in disc.PATHS:
        assert path in paths, path
        assert path in text, path


def test_the_handler_answers_its_own_paths_and_nothing_else():
    """Content type is part of the answer.

    `llms.txt` is prose and the other two are JSON. A handler that returns
    one shape for all three would be read by a client as a broken document
    rather than as a wrong header.
    """
    body, ctype, code = disc.handle_discovery_get(disc.LLMS_PATH)
    assert code == 200 and ctype.startswith("text/plain")
    assert body.decode("utf-8").startswith("# Flywheel gateway")
    for path in (disc.OPENAPI_PATH, disc.CARD_PATH):
        body, ctype, code = disc.handle_discovery_get(path)
        assert code == 200 and ctype == "application/json"
        assert json.loads(body)
    assert disc.handle_discovery_get("/api/world") is None


def test_the_openapi_document_is_shaped_like_openapi():
    """Enough structure that a generator can read it.

    Not a full schema validation. What is checked is what a client actually
    trips over: the version, a security scheme the private routes reference,
    and at least one described method per path.
    """
    doc = disc.openapi_document()
    assert doc["openapi"].startswith("3.1")
    assert doc["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert len(doc["paths"]) > 100
    for path, entry in doc["paths"].items():
        methods = [k for k in entry if k in
                   ("get", "post", "put", "delete", "head")]
        assert methods, path
        for name in methods:
            assert entry[name]["summary"], f"{name} {path}"
            assert entry[name]["responses"], f"{name} {path}"
            assert not entry[name].get("x-flywheel-undescribed"), path


def test_a_prefix_route_is_written_as_a_prefix_and_says_so():
    """OpenAPI has no way to say "everything under here".

    The `{subpath}` parameter is the nearest shape, and a reader who takes it
    for a normal path parameter would build the wrong client, so the match
    kind is stated rather than implied by the braces.
    """
    doc = disc.openapi_document()["paths"]
    prefixes = {p for p, e in doc.items() if e["x-flywheel-match"] == PREFIX}
    assert prefixes, "the gateway serves prefix routes and none were marked"
    for path in prefixes:
        assert path.endswith("{subpath}")
        params = doc[path]["parameters"]
        assert params[0]["name"] == "subpath" and params[0]["required"]


def test_llms_txt_holds_every_route_in_the_llmstxt_shape():
    """H1, a blockquote summary, then link lists. And no route left out."""
    text = disc.llms_txt()
    lines = text.splitlines()
    assert lines[0].startswith("# ")
    assert any(line.startswith("> ") for line in lines[:6])
    assert any(line.startswith("## ") for line in lines)
    for route in gateway_routes():
        assert f"]({route.path})" in text, route.path
    assert "](/api/writing/init/prepare)" in text
    assert "descriptor-backed Writing operation paths" in text


def test_the_card_counts_what_it_points_at():
    """The card carries the numbers a caller would otherwise have to derive,
    and they have to be the same numbers the other documents were built from."""
    routes = gateway_routes()
    descriptor_paths = {op.http_path for op in http_operations()}
    card = disc.card()
    assert card["schema"] == disc.SCHEMA
    assert card["routes"] == len(disc.openapi_document()["paths"])
    assert card["dispatcher_routes"] == len(routes)
    assert card["descriptor_backed_routes"] == len(descriptor_paths)
    assert card["typed_route_scope"] == ["writing operations"]
    assert card["undescribed"] == len(undescribed(routes)) == 0
    assert card["discovery"]["openapi"] == disc.OPENAPI_PATH
    assert card["discovery"]["llms_txt"] == disc.LLMS_PATH


def test_the_gateway_actually_serves_the_three_documents():
    """Everything above tests the builders. This tests the wiring.

    A dispatch literal with no handler behind it would satisfy every other
    test here, because the inventory is parsed from the literal. So one real
    socket, three real requests, and the content types checked on the wire.
    """
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from harness.gateway import _Handler

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + disc.LLMS_PATH, timeout=10) as r:
            assert r.status == 200
            assert r.headers.get("Content-Type").startswith("text/plain")
            assert r.read().decode("utf-8").startswith("# Flywheel gateway")
        for path in (disc.OPENAPI_PATH, disc.CARD_PATH):
            with urllib.request.urlopen(base + path, timeout=10) as r:
                assert r.status == 200, path
                assert r.headers.get("Content-Type") == "application/json"
                assert json.loads(r.read())["schema" if path == disc.CARD_PATH
                                            else "openapi"]
    finally:
        server.shutdown()
        server.server_close()


def test_the_version_is_resolved_and_not_typed_into_the_documents():
    """A version repeated by hand in three generated documents is a release
    step somebody forgets. All three read the same resolver."""
    version = disc.installed_version()
    assert version and version != "0"
    assert disc.card()["version"] == version
    assert disc.openapi_document()["info"]["version"] == version
    assert version in disc.llms_txt().splitlines()[0]
