"""MCP tool definitions and handlers for series review and the author's voice.

All six tools are local and read-only. They read the text the host passes
and, for voice_compare, voice_apply_plan and interview with voice_name, one
voice file the author saved with the command line plus the store's identity
file. A profile that belongs to another owner is refused. No tool takes samples
to learn from: learning through a tool would put the samples into the host
conversation, so learning stays on the command line. No tool exports, imports
or deletes a profile.
"""
from .tool_text import description

NAMES = ("corpus_check", "title_workshop", "interview", "restructure_plan", "voice_compare",
         "voice_apply_plan")
_TEXT = {"type": "string", "description": "the passage to read"}
_VOICE = {"type": "string", "description": "name of a voice saved with articulate voice learn"}
_SCHEMAS = {
    "corpus_check": {"type": "object", "required": ["documents"], "properties": {
        "documents": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["name", "text"],
            "properties": {"name": {"type": "string"}, "text": {"type": "string"},
                           "title": {"type": "string"}}}},
        "keep": {"type": "array", "items": {"type": "string"},
                 "description": "phrases and headings repeated on purpose"},
        "genre": {"type": "string", "default": "essay"},
        "single": {"type": "boolean", "default": False}}},
    "title_workshop": {"type": "object", "required": ["titles"], "properties": {
        "titles": {"type": "array", "items": {"type": "string"}},
        "answers": {"type": "array", "items": {"type": "string"},
                    "description": "the author's one-line answer per title, in order"}}},
    "interview": {"type": "object", "required": ["text"],
                  "properties": {"text": _TEXT, "voice_name": _VOICE}},
    "restructure_plan": {"type": "object", "required": ["text"], "properties": {
        "text": _TEXT, "anchors": {"type": "string", "enum": ["footnote", "link"],
                                   "default": "footnote"}}},
    "voice_compare": {"type": "object", "required": ["text", "voice_name"],
                      "properties": {"text": _TEXT, "voice_name": _VOICE}},
    "voice_apply_plan": {"type": "object", "required": ["text", "voice_name", "authored_by_user"],
                         "properties": {
                             "text": {"type": "string", "description": "the user's own draft"},
                             "voice_name": _VOICE,
                             "authored_by_user": {"type": "boolean", "description":
                                                  "true only when the user says the draft is theirs"},
                             "author_text": {"type": "string", "description":
                                             "the user's own words the edit may add"}}},
}
TOOLS = [{"name": n, "description": description(n, {}), "inputSchema": _SCHEMAS[n]} for n in NAMES]


def _string(args, key, required=True):
    value = args.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f"'{key}' is required and must be a string")
    return value


def _strings(args, key):
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"'{key}' must be a list of strings")
    return value


def _voice(args, required):
    from . import voice_identity, voice_store
    name = _string(args, "voice_name", required)
    if not name:
        return None
    profile = voice_store.load(name)
    voice_identity.check_owner(profile)
    return profile


def _corpus_check(args):
    from . import corpus, corpus_receipt
    docs, single = args.get("documents"), bool(args.get("single", False))
    keep, genre = _strings(args, "keep") or (), args.get("genre", "essay")
    report = corpus.analyze_corpus(docs, keep=keep, genre=genre, single=single)
    receipt = corpus_receipt.make_corpus_receipt(docs, keep=report["keep"], genre=genre,
                                                 single=single, report=report)
    return dict(report, receipt=receipt)


def _title_workshop(args):
    from . import titles
    return titles.workshop(_strings(args, "titles"), answers=_strings(args, "answers"))


def _interview(args):
    from . import interview
    return interview.questions(_string(args, "text"), voice_profile=_voice(args, False))


def _restructure(args):
    from . import restructure
    return restructure.propose(_string(args, "text"), anchors=args.get("anchors", "footnote"))


def _voice_compare(args):
    from . import voice
    text = _string(args, "text")
    return voice.compare(text, _voice(args, True))


def _voice_apply_plan(args):
    from . import voice_apply
    return voice_apply.plan(_string(args, "text"), _string(args, "voice_name"),
                            authored_by_user=args.get("authored_by_user"),
                            author_text=_string(args, "author_text", False))


_HANDLERS = {"voice_apply_plan": _voice_apply_plan, "corpus_check": _corpus_check, "title_workshop": _title_workshop,
             "interview": _interview, "restructure_plan": _restructure,
             "voice_compare": _voice_compare}


def handle(name, args):
    """Run one tool. Raises ValueError or FileNotFoundError on bad input."""
    return _HANDLERS[name](args)
