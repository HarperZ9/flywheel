import io
import json


class _ReadLog(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw)
        self.calls = []

    def read(self, n=-1):
        before = self.tell()
        out = super().read(n)
        self.calls.append((n, before, self.tell(), len(out)))
        return out


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _Handler:
    def __init__(self, raw=b"{}"):
        self.rfile = io.BytesIO(raw)
        self.headers = _Headers({"Content-Length": str(len(raw))})
        self.root = "."
        self.owner_ref = "owner_" + "a" * 32
        self.flywheel_home = None
        self.clock = lambda: "2026-09-13T08:00:00Z"
        self.reads = 0

    def _content_length(self):
        return int(self.headers["Content-Length"])

    def _req_json(self):
        self.reads += 1
        return json.loads(self.rfile.read(self._content_length()) or b"{}"), None


def test_api_import_still_uses_existing_config_import_behavior(monkeypatch):
    from harness.import_route import handle_import_post

    handler = _Handler(json.dumps({"root": "."}).encode())
    monkeypatch.setattr("harness.import_route._resolve_import_root",
                        lambda _h, requested: ("resolved", None))
    monkeypatch.setattr("harness.import_route.import_config",
                        lambda root: {"schema": "imported", "root": root})
    monkeypatch.setattr("harness.import_route.put_entity",
                        lambda kind, doc: {"eid": "eid1"})

    body, status = handle_import_post("/api/import", handler)

    assert status == 200
    assert body == {"schema": "imported", "root": "resolved", "stored": "eid1"}
    assert handler.reads == 1


def test_api_import_inspect_dispatches_raw_upload_without_json_reader(monkeypatch):
    from harness.import_route import handle_import_post

    handler = _Handler(b"not-json")
    monkeypatch.setattr("harness.import_route.handle_inspect_upload",
                        lambda h: ({"schema": "inspect"}, 200))

    assert handle_import_post("/api/import/inspect", handler) == ({"schema": "inspect"}, 200)
    assert handler.reads == 0
    assert handle_import_post("/api/other", handler) is None


def test_gateway_post_dispatches_inspect_upload_before_generic_action(monkeypatch, tmp_path):
    from harness import gateway
    import harness.gateway_operation as gateway_operation

    raw = b"raw inspect bytes"
    stream = _ReadLog(raw)
    captured = {}
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/import/inspect"
    handler.headers = _Headers({"Content-Length": str(len(raw))})
    handler.rfile = stream
    handler.owner_ref = "owner_" + "a" * 32
    handler.flywheel_home = tmp_path / "home"
    handler.root = tmp_path
    handler.clock = lambda: "2026-09-13T08:00:00Z"
    handler._json = lambda body, code=200: captured.update(body=body, code=code)

    def upload(h):
        length = h._content_length()
        return {"read": h.rfile.read(length).decode()}, 200

    monkeypatch.setattr("harness.import_route.handle_inspect_upload", upload)
    monkeypatch.setattr(gateway_operation, "action_for_path",
                        lambda _path: (_ for _ in ()).throw(AssertionError("generic reader used")))

    handler._post()

    assert captured == {"body": {"read": raw.decode()}, "code": 200}
    assert stream.calls == [(len(raw), 0, len(raw), len(raw))]


def test_gateway_get_dispatches_private_inspect_read_route(monkeypatch, tmp_path):
    from harness import gateway
    from harness.gateway_custody import is_private

    assert is_private("/api/import/inspect")
    assert is_private("/api/import/inspect/eid1")
    captured = {}
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/import/inspect/eid1"
    handler.owner_ref = "owner_" + "a" * 32
    handler.flywheel_home = tmp_path / "home"
    handler._json = lambda body, code=200: captured.update(body=body, code=code)
    monkeypatch.setattr("harness.import_route.handle_import_get",
                        lambda path, h, query="": ({"path": path, "owner": h.owner_ref}, 200))

    handler._get()

    assert captured == {"body": {"path": "/api/import/inspect/eid1",
                                 "owner": "owner_" + "a" * 32}, "code": 200}
