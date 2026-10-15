"""ci_stub_model.py -- a scripted OpenAI-compatible model for CI smoke runs.

Serves POST /v1/chat/completions on 127.0.0.1:PORT and answers with the next
reply from a fixed script, then the last one forever. It exists so the GitHub
Action can be exercised end to end without a model account. Standard library.

  python scripts/ci_stub_model.py 8099 'TOOL write_file {...}' 'Done.'
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLIES: list = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        text = REPLIES.pop(0) if len(REPLIES) > 1 else REPLIES[0]
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": text},
                                        "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main(argv: list) -> int:
    port, replies = int(argv[0]), argv[1:]
    REPLIES.extend(replies or ["Done."])
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
