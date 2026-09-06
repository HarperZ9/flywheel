"""A scripted LSP server for tests. Run as: python tests/fake_lsp_server.py

Hand-written on raw pipes on purpose. If this spoke through harness/lsp_wire.py
it would agree with the client about framing even when both were wrong, and the
wire tests would pass on a protocol nobody else can read.

What it answers is deliberately small and fixed: a definition at line 2, two
references at lines 1 and 4, a hover, and a highlight that echoes back whatever
position it was sent. That last one is the encoding control. A client counting
characters the wrong way sends a different number, and the echo makes the
difference visible instead of returning a plausible location.

Flags:
  --encoding NAME     answer initialize with this positionEncoding
  --ask-configuration request workspace/configuration once, after initialized
  --never-publish     say nothing about any file, ever. A server that has not
                      spoken is the case a caller must not read as clean.
  --pull              advertise a diagnosticProvider and push nothing, the way
                      a 3.17 server does. Diagnostics come only when asked for.
  --pull-unchanged    answer the pull request with an unchanged report, which
                      says nothing new and, to a client holding no previous
                      report, says nothing at all.
"""

import json
import sys

CAPABILITIES = {
    "textDocumentSync": {"openClose": True, "change": 1},
    "definitionProvider": True,
    "referencesProvider": True,
    "hoverProvider": True,
    "documentHighlightProvider": True,
}


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


def reply(msg, result):
    send({"jsonrpc": "2.0", "id": msg["id"], "result": result})


def items_for(text):
    """One diagnostic for any buffer holding the word this server dislikes."""
    return ([{"range": {"start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 6}},
              "severity": 1, "message": "fake: broken symbol"}]
            if "broken" in text else [])


def publish(uri, text, version):
    """Push a set, unless this run is a server that only answers when asked."""
    if never_publish or pull:
        return
    params = {"uri": uri, "diagnostics": items_for(text)}
    if version is not None:
        params["version"] = version
    send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
          "params": params})


def diagnostic_report(text):
    """A DocumentDiagnosticReport, in whichever of its two kinds was asked for."""
    if pull_unchanged:
        return {"kind": "unchanged", "resultId": "same-as-before"}
    return {"kind": "full", "resultId": "r1", "items": items_for(text)}


def span(start, end):
    return {"start": start, "end": end}


def at(line, start, end):
    return span({"line": line, "character": start},
                {"line": line, "character": end})


encoding = None
ask_configuration = False
never_publish = "--never-publish" in sys.argv
pull_unchanged = "--pull-unchanged" in sys.argv
pull = pull_unchanged or "--pull" in sys.argv
if "--encoding" in sys.argv:
    encoding = sys.argv[sys.argv.index("--encoding") + 1]
if "--ask-configuration" in sys.argv:
    ask_configuration = True

opened = {}
next_id = 1000

while True:
    msg = read_message()
    if msg is None:
        break
    if "method" not in msg:
        # A response to something this server asked for. Reported as a log
        # message so a test can see the reverse direction completed, rather
        # than inferring it from the absence of a hang.
        send({"jsonrpc": "2.0", "method": "window/logMessage",
              "params": {"type": 3,
                         "message": "configuration answered: %s"
                                    % json.dumps(msg.get("result"))}})
        continue
    method = msg["method"]
    params = msg.get("params") or {}
    document = params.get("textDocument") or {}
    uri = document.get("uri", "")

    if method == "initialize":
        capabilities = dict(CAPABILITIES)
        if pull:
            capabilities["diagnosticProvider"] = {
                "identifier": "fake", "interFileDependencies": False,
                "workspaceDiagnostics": False}
        if encoding is not None:
            capabilities["positionEncoding"] = encoding
        reply(msg, {"capabilities": capabilities,
                    "serverInfo": {"name": "fake", "version": "1"}})
    elif method == "initialized":
        if ask_configuration:
            send({"jsonrpc": "2.0", "id": next_id,
                  "method": "workspace/configuration",
                  "params": {"items": [{"section": "fake"}]}})
            next_id += 1
    elif method == "textDocument/didOpen":
        opened[uri] = document.get("text", "")
        publish(uri, opened[uri], document.get("version"))
    elif method == "textDocument/didChange":
        for change in params.get("contentChanges") or []:
            opened[uri] = change.get("text", "")
        publish(uri, opened.get(uri, ""), document.get("version"))
    elif method == "textDocument/didClose":
        opened.pop(uri, None)
    elif method == "textDocument/definition":
        reply(msg, [{"uri": uri, "range": at(2, 4, 9)}])
    elif method == "textDocument/references":
        reply(msg, [{"uri": uri, "range": at(1, 0, 5)},
                    {"uri": uri, "range": at(4, 2, 7)}])
    elif method == "textDocument/diagnostic":
        reply(msg, diagnostic_report(opened.get(uri, "")))
    elif method == "textDocument/hover":
        reply(msg, {"contents": {"kind": "plaintext", "value": "fake hover"}})
    elif method == "textDocument/documentHighlight":
        # The echo. Whatever position arrived comes straight back, so a test can
        # compare it against the character the client meant to name.
        position = params.get("position") or {}
        reply(msg, [{"range": span(position, position), "kind": 1}])
    elif method == "shutdown":
        reply(msg, None)
    elif method == "exit":
        break
    elif "id" in msg:  # any other request: a result the caller can read as none
        reply(msg, None)
