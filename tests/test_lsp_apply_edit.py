"""What this client does when a server pushes it a WorkspaceEdit.

The module under test decides whether an edit is applicable. This is about the
decision above that one: whether this particular client is allowed to write at
all, whether it knows the tree it is confined to, and whether the server is told
afterwards what its buffers now hold.
"""
from harness.lsp_capabilities import client_capabilities, initialize_params
from harness.lsp_client import LspClient
from harness.lsp_documents import to_uri


def span(line, start, end, new_text):
    return {"range": {"start": {"line": line, "character": start},
                      "end": {"line": line, "character": end}},
            "newText": new_text}


def write(tmp_path, name, text):
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def changes(path, *edits):
    return {"changes": {to_uri(path): list(edits)}}


class Stub:
    """A connection that answers initialize and records what was notified."""

    def __init__(self) -> None:
        self.handler = None
        self.sent = None
        self.notified: list[str] = []

    def call(self, method, params=None, timeout=None):
        self.sent = params
        return {"capabilities": {
            "textDocumentSync": {"openClose": True, "change": 1}}}

    def notify(self, method, params=None):
        self.notified.append(method)

    def close(self, reason=None):
        pass


def started(tmp_path, *, apply_edit):
    connection = Stub()
    client = LspClient(connection, root=tmp_path)
    client.apply_edit = apply_edit
    client.initialize()
    return client, connection


def test_a_client_that_did_not_declare_applyedit_says_no_and_writes_nothing(
        tmp_path):
    path = write(tmp_path, "a.py", "one\n")
    client, connection = started(tmp_path, apply_edit=False)
    reply = connection.handler.on_request(
        "workspace/applyEdit", {"edit": changes(path, span(0, 0, 3, "ONE"))})
    assert reply["applied"] is False
    assert "write-not-allowed" in reply["failureReason"]
    assert path.read_text(encoding="utf-8") == "one\n"
    assert connection.sent["capabilities"]["workspace"]["applyEdit"] is False
    assert client.edit_records == []


def test_a_declared_client_applies_the_edit_and_resyncs_the_buffer(tmp_path):
    """The server has to be told, or its next answer describes text that moved.

    didChange is the observable. Without it the server keeps answering about
    the buffer it last saw, and every position it returns is measured against a
    document this client already rewrote.
    """
    path = write(tmp_path, "a.py", "one\n")
    client, connection = started(tmp_path, apply_edit=True)
    uri = client.open(path, "python")
    reply = connection.handler.on_request(
        "workspace/applyEdit", {"edit": changes(path, span(0, 0, 3, "ONE"))})
    assert reply == {"applied": True}
    assert path.read_text(encoding="utf-8") == "ONE\n"
    assert "textDocument/didChange" in connection.notified
    assert client.documents.get(uri).text == "ONE\n"
    assert client.edit_records[-1]["applied"] is True
    assert connection.sent["capabilities"]["workspace"]["applyEdit"] is True


def test_a_refusal_is_answered_rather_than_raised_and_is_recorded(tmp_path):
    path = write(tmp_path, "a.py", "one\n")
    client, connection = started(tmp_path, apply_edit=True)
    reply = connection.handler.on_request("workspace/applyEdit", {"edit": {
        "changes": {to_uri(path): [span(0, 0, 3, "x"), span(0, 1, 3, "y")]}}})
    assert reply["applied"] is False
    assert "overlapping-edits" in reply["failureReason"]
    assert path.read_text(encoding="utf-8") == "one\n"
    assert client.edit_records[-1]["reason"] == "overlapping-edits"


def test_a_client_with_no_workspace_root_refuses(tmp_path):
    """With no root every path is inside it, so there is nothing to contain."""
    path = write(tmp_path, "a.py", "one\n")
    connection = Stub()
    client = LspClient(connection)
    client.apply_edit = True
    client.initialize()
    reply = connection.handler.on_request(
        "workspace/applyEdit", {"edit": changes(path, span(0, 0, 3, "ONE"))})
    assert reply["applied"] is False
    assert "outside-root" in reply["failureReason"]
    assert path.read_text(encoding="utf-8") == "one\n"


def test_the_declared_capability_tracks_the_flag_that_governs_the_write():
    """A declaration that does not match the behaviour is worse than silence."""
    assert client_capabilities()["workspace"]["applyEdit"] is False
    assert client_capabilities(apply_edit=True)["workspace"]["applyEdit"] is True
    params = initialize_params(None, process_id=1, client_name="t",
                               client_version="0", apply_edit=True)
    assert params["capabilities"]["workspace"]["applyEdit"] is True


def test_the_client_declares_no_resource_operations_because_it_performs_none():
    edit = client_capabilities()["workspace"]["workspaceEdit"]
    assert edit["resourceOperations"] == []
    assert edit["documentChanges"] is True
    assert edit["failureHandling"] == "abort"
