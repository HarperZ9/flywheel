"""A minimal scripted LSP server for tests: speaks Content-Length framing,
answers initialize, records didOpen/didChange, and returns a fixed
definition location. Run as: python tests/fake_lsp_server.py"""

import json
import sys


def read_message():
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
    if length is None:
        return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def send(msg):
    body = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n%b" % (len(body), body))
    sys.stdout.buffer.flush()


opened = {}

while True:
    msg = read_message()
    if msg is None:
        break
    method = msg.get("method", "")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"],
              "result": {"capabilities": {"definitionProvider": True}}})
    elif method == "textDocument/didOpen":
        opened[msg["params"]["textDocument"]["uri"]] = \
            msg["params"]["textDocument"]["text"]
    elif method == "textDocument/definition":
        uri = msg["params"]["textDocument"]["uri"]
        send({"jsonrpc": "2.0", "id": msg["id"],
              "result": [{"uri": uri,
                          "range": {"start": {"line": 2, "character": 4},
                                    "end": {"line": 2, "character": 9}}}]})
    elif method == "textDocument/hover":
        send({"jsonrpc": "2.0", "id": msg["id"],
              "result": {"contents": {"kind": "plaintext",
                                      "value": "fake hover"}}})
    elif "id" in msg:  # any other request: empty result
        send({"jsonrpc": "2.0", "id": msg["id"], "result": None})
