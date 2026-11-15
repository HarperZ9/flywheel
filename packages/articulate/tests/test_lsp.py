import io
import json

from articulate import lsp_server as L


def _frame(msg):
    b = json.dumps(msg).encode("utf-8")
    return f"Content-Length: {len(b)}\r\n\r\n".encode("ascii") + b


def _parse(data):
    out, i = [], 0
    while i < len(data):
        hdr_end = data.find(b"\r\n\r\n", i)
        if hdr_end < 0:
            break
        header = data[i:hdr_end].decode("ascii")
        length = int(next(h for h in header.split("\r\n")
                          if h.lower().startswith("content-length")).split(":")[1])
        start = hdr_end + 4
        out.append(json.loads(data[start:start + length].decode("utf-8")))
        i = start + length
    return out


def _run(messages):
    stdin = b"".join(_frame(m) for m in messages)
    out = io.BytesIO()
    L.serve(io.BytesIO(stdin), out)
    return _parse(out.getvalue())


URI = "file:///C:/tmp/doc.md"
SLOP = ("In today's landscape, AI is not just a tool, but a force. "
        "You can watch what a model does. You cannot watch what it is.")


def test_initialize_advertises_sync():
    msgs = _run([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "exit", "params": {}},
    ])
    init = next(m for m in msgs if m.get("id") == 1)
    assert init["result"]["capabilities"]["textDocumentSync"]["openClose"] is True


def test_didopen_publishes_diagnostics_with_ranges():
    msgs = _run([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {
            "textDocument": {"uri": URI, "languageId": "markdown", "version": 1, "text": SLOP}}},
        {"jsonrpc": "2.0", "method": "exit", "params": {}},
    ])
    diag = next(m for m in msgs if m.get("method") == "textDocument/publishDiagnostics")
    ds = diag["params"]["diagnostics"]
    assert diag["params"]["uri"] == URI
    assert len(ds) >= 3
    for d in ds:
        assert d["source"] == "articulate"
        assert d["severity"] in (2, 3, 4)
        r = d["range"]
        assert r["end"]["character"] >= r["start"]["character"]


def test_didclose_clears_diagnostics():
    msgs = _run([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "textDocument/didClose", "params": {
            "textDocument": {"uri": URI}}},
        {"jsonrpc": "2.0", "method": "exit", "params": {}},
    ])
    diag = next(m for m in msgs if m.get("method") == "textDocument/publishDiagnostics")
    assert diag["params"]["diagnostics"] == []
