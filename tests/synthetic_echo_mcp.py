"""Tiny stdio MCP server used only by gateway MCP admission tests."""
import json
import sys


TOOL = {"name": "echo", "description": "Echo a message.",
    "inputSchema": {"type": "object",
        "properties": {"msg": {"type": "string"}}, "required": ["msg"],
        "additionalProperties": False}}


def _reply(identifier, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": identifier}
    if error is None:
        msg["result"] = result or {}
    else:
        msg["error"] = {"code": -32000, "message": error}
    print(json.dumps(msg), flush=True)


def main():
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        identifier = msg.get("id")
        if identifier is None:
            continue
        if method == "initialize":
            _reply(identifier, {"protocolVersion": "2025-06-18",
                "serverInfo": {"name": "synthetic-stdio", "version": "1"},
                "capabilities": {}})
        elif method == "tools/list":
            _reply(identifier, {"tools": [TOOL]})
        elif method == "tools/call":
            params = msg.get("params") or {}
            args = params.get("arguments") if type(params.get("arguments")) is dict else {}
            if params.get("name") != "echo":
                _reply(identifier, error="unknown tool")
            else:
                _reply(identifier, {"content": [{"type": "text",
                    "text": "echo: " + str(args.get("msg", ""))}]})
        else:
            _reply(identifier, error="unknown method")


if __name__ == "__main__":
    main()
