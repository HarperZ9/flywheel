"""The house-voice hook for agent harnesses: SessionStart and Stop.

SessionStart (sources startup, resume, clear and compact): returns the brief as
additional context, so the model writes in the house voice from its first
token and again after a compaction. It reads the packaged spec and the settings
file and imports none of the style rules, so it costs about one Python start.

Stop: only in mode revise. When the event carries the final reply
(last_assistant_message) and that reply claims a human life or holds a HIGH
style finding, the hook asks for one revision and names each finding by line.
When stop_hook_active is true it says nothing, so a reply is revised at most
once. Without the reply text in the event it says nothing; it never opens the
transcript.

Every path exits 0. With the mode off it prints nothing. It reads stdin, the
spec and the settings file, writes only its answer to stdout, opens no network
connection, starts no program and never reads the personal voice store.
"""
import json
import sys

from . import house_settings, house_spec

MAX_EVENT_BYTES = 4 * 1024 * 1024
MAX_REPLY_CHARS = 200_000
MAX_FINDINGS = 8


def _session_start(settings):
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": house_spec.session_context(settings)}}


def _stop(event, settings):
    if settings["mode"] != "revise" or event.get("stop_hook_active") is True:
        return None
    reply = event.get("last_assistant_message")
    if not isinstance(reply, str) or not reply.strip() or len(reply) > MAX_REPLY_CHARS:
        return None
    from . import house  # the style rules load only on this path
    found = house.revision_findings(reply)
    if not found:
        return None
    lines = ["L%d %s: %s (%r)" % (f["line"], f["category"], f["reason"], f["match"])
             for f in found[:MAX_FINDINGS]]
    if len(found) > MAX_FINDINGS:
        lines.append("and %d more" % (len(found) - MAX_FINDINGS))
    reason = ("Articulate house voice (%s): revise your last reply once. Keep every fact, "
              "number, code block, quote and disclosure. Findings:\n%s\nIf a finding is "
              "wrong, keep the sentence and say why in one line."
              % (house_spec.spec()["version"], "\n".join(lines)))
    return {"decision": "block", "reason": reason}


def respond(raw, environ=None):
    """The JSON a hook prints for raw stdin bytes, or None."""
    settings = house_settings.resolve(environ)
    if settings["mode"] == "off":
        return None
    if len(raw) > MAX_EVENT_BYTES:
        raise ValueError("hook event is over the %d byte limit" % MAX_EVENT_BYTES)
    event = json.loads(raw.decode("utf-8")) if raw.strip() else None
    if not isinstance(event, dict):
        return None
    name = event.get("hook_event_name")
    if name == "SessionStart":
        answer = _session_start(settings)
    elif name == "Stop":
        answer = _stop(event, settings)
    else:
        answer = None
    return None if answer is None else json.dumps(answer)


def main(stdin=None, stdout=None, stderr=None):
    """Run once as a hook command. Always returns 0."""
    stdin = stdin or sys.stdin.buffer
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    try:
        answer = respond(stdin.read(MAX_EVENT_BYTES + 1))
    except Exception as exc:  # advisory hook: report, never block the session
        stderr.write("articulate house hook skipped this event: %s: %s\n" % (type(exc).__name__, exc))
        return 0
    if answer is not None:
        stdout.write(answer + "\n")
        stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
