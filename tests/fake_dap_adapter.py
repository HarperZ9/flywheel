"""A scripted debug adapter for tests. Run as: python tests/fake_dap_adapter.py

Hand-written on raw pipes on purpose. If this spoke through harness/dap_wire.py
it would agree with the client about the envelope even when both were wrong, and
the wire tests would pass on a protocol no real adapter can read.

It debugs nothing. What it does is answer in the shapes the specification
defines, including the shapes a client gets wrong: an unverified breakpoint, a
breakpoint the adapter moved to another line, an expensive scope, and a stack
that reports more frames than it returned.

Flags:
  --late-launch     answer `launch` only after `configurationDone`, which is the
                    ordering that deadlocks a client that waits on the launch
                    response before configuring. Half of real adapters do this.
  --ask-terminal    send a runInTerminal reverse request during configuration
                    and report in an output event what the client answered.
  --no-config-done  do not advertise supportsConfigurationDoneRequest, and fail
                    the request if it is sent anyway. A client that sends it
                    unconditionally fails here rather than in the field.
  --launch-fails    answer `launch` with success false and never send
                    `initialized`. A client waiting on the event alone hangs.
  --die             write a reason to stderr and exit before reading anything,
                    the way an adapter with no runtime behind it does.
"""

import json
import sys

VERIFIED_LINES = (10, 20)
MOVED_FROM, MOVED_TO = 30, 31

CAPABILITIES = {
    "supportsConfigurationDoneRequest": True,
    "supportsTerminateRequest": True,
    "supportsEvaluateForHovers": True,
    "supportsConditionalBreakpoints": False,
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


def send(message):
    message["seq"] = next_seq()
    body = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n%b" % (len(body), body))
    sys.stdout.buffer.flush()


_seq = [0]


def next_seq():
    _seq[0] += 1
    return _seq[0]


def reply(message, body=None):
    answer = {"type": "response", "request_seq": message["seq"], "success": True,
              "command": message["command"]}
    if body is not None:
        answer["body"] = body
    send(answer)


def refuse(message, text):
    send({"type": "response", "request_seq": message["seq"], "success": False,
          "command": message["command"], "message": text,
          "body": {"error": {"id": 1, "format": text, "showUser": False}}})


def event(name, body=None):
    message = {"type": "event", "event": name}
    if body is not None:
        message["body"] = body
    send(message)


def breakpoints_for(arguments):
    """One placed breakpoint per requested line, in the four shapes that exist.

    A verified breakpoint, an unverified one with a reason, and one the adapter
    moved to a different line. A client that reports what it asked for rather
    than what came back gets all three wrong.
    """
    placed = []
    for index, wanted in enumerate(arguments.get("breakpoints") or []):
        line = wanted.get("line")
        entry = {"id": index + 1, "line": line, "verified": line in VERIFIED_LINES}
        if line == MOVED_FROM:
            entry.update({"verified": True, "line": MOVED_TO})
        elif not entry["verified"]:
            entry["message"] = "no code on that line"
        placed.append(entry)
    return {"breakpoints": placed}


def stack_trace(arguments):
    """Five frames, paged the way the request asked for them.

    A client that reads one page and does not carry `totalFrames` back reports a
    truncated stack as a complete one, which is the wrong answer to the question
    a debugger is usually opened to answer.
    """
    frames = [{"id": index + 1, "name": f"frame{index}", "line": 10 * index + 1,
               "column": 1, "source": {"path": "program.py"}}
              for index in range(5)]
    start = arguments.get("startFrame") or 0
    levels = arguments.get("levels") or len(frames)
    return {"stackFrames": frames[start:start + levels], "totalFrames": 5}


def scopes(_arguments):
    return {"scopes": [
        {"name": "Locals", "variablesReference": 1000, "expensive": False},
        {"name": "Globals", "variablesReference": 1001, "expensive": True},
    ]}


def variables(arguments):
    if arguments.get("variablesReference") == 1000:
        return {"variables": [
            {"name": "total", "value": "42", "type": "int",
             "variablesReference": 0},
            {"name": "items", "value": "list(3)", "type": "list",
             "variablesReference": 1002},
        ]}
    # An expensive scope a client should not have read. Answering with a marker
    # rather than an error means the test sees the value in the record if the
    # client read it anyway.
    return {"variables": [{"name": "expensive_was_read", "value": "true",
                           "variablesReference": 0}]}


def main():
    flags = set(sys.argv[1:])
    if "--die" in flags:
        sys.stderr.write("adapter cannot start: no runtime found\n")
        sys.stderr.flush()
        return
    late = "--late-launch" in flags
    capabilities = dict(CAPABILITIES)
    if "--no-config-done" in flags:
        capabilities["supportsConfigurationDoneRequest"] = False
    held_launch = None

    while True:
        message = read_message()
        if message is None:
            return
        if message.get("type") == "response":
            # The client answered a reverse request. Report what it said, so a
            # refusal is observable from the adapter's side of the wire too.
            outcome = "allowed" if message.get("success") else "refused"
            event("output", {"category": "console",
                             "output": f"runInTerminal {outcome}\n"})
            continue
        command = message.get("command")
        arguments = message.get("arguments") or {}

        if command == "initialize":
            reply(message, capabilities)
            if "--launch-fails" not in flags:
                event("initialized")
        elif command in ("launch", "attach"):
            if "--launch-fails" in flags:
                refuse(message, "the program could not be started")
            elif late:
                held_launch = message
            else:
                reply(message)
        elif command == "setBreakpoints":
            reply(message, breakpoints_for(arguments))
            if "--ask-terminal" in flags:
                send({"type": "request", "command": "runInTerminal",
                      "arguments": {"kind": "integrated", "title": "debuggee",
                                    "cwd": ".", "args": ["python", "program.py"]}})
        elif command == "setExceptionBreakpoints":
            reply(message, {"breakpoints": []})
        elif command == "configurationDone":
            if not capabilities["supportsConfigurationDoneRequest"]:
                refuse(message, "this adapter does not take configurationDone")
                continue
            reply(message)
            if held_launch is not None:
                reply(held_launch)
                held_launch = None
            event("stopped", {"reason": "breakpoint", "threadId": 1,
                              "allThreadsStopped": True,
                              "hitBreakpointIds": [1]})
        elif command == "threads":
            reply(message, {"threads": [{"id": 1, "name": "MainThread"}]})
        elif command == "stackTrace":
            reply(message, stack_trace(arguments))
        elif command == "scopes":
            reply(message, scopes(arguments))
        elif command == "variables":
            reply(message, variables(arguments))
        elif command == "evaluate":
            # Echoes the context back, which is the control on a client that
            # says it evaluates read-only and then sends the repl context.
            reply(message, {"result": f"{arguments.get('expression')} in "
                                      f"{arguments.get('context')}",
                            "variablesReference": 0})
        elif command == "continue":
            reply(message, {"allThreadsContinued": True})
            event("terminated")
            event("exited", {"exitCode": 0})
        elif command in ("next", "stepIn", "stepOut"):
            reply(message)
            event("stopped", {"reason": "step", "threadId": 1})
        elif command in ("terminate", "disconnect"):
            reply(message)
            if command == "disconnect":
                return
        else:
            refuse(message, f"unsupported request {command}")


if __name__ == "__main__":
    main()
