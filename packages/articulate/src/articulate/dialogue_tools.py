"""MCP tool definition and handler for the dialogue and character voice audit.

dialogue_check is local and read-only. It reads the script text and any voice
sheets the host passes and returns the report; it opens no file and writes
nothing. The command line, `articulate dialogue`, reads files and folders.
"""
from . import dialogue, dialogue_parse, dialogue_sheet
from .tool_text import description

NAMES = ("dialogue_check",)
_SCHEMAS = {
    "dialogue_check": {"type": "object", "required": ["text"], "properties": {
        "text": {"type": "string", "description": "script text: LWD lines, NAME: text lines, "
                                                  "or a printed play"},
        "format": {"type": "string", "enum": ["auto", "lwd", "colon", "play"], "default": "auto"},
        "voices": {"type": "array", "items": {"type": "object"},
                   "description": "character voice sheets (articulate-voice-sheet/1 objects)"},
        "theme_words": {"type": "array", "items": {"type": "string"}},
        "min_lines": {"type": "integer", "minimum": 2, "default": 20,
                      "description": "lines a speaker needs to be scored for attribution"},
        "worst": {"type": "integer", "minimum": 0, "default": 30}}},
}
TOOLS = [{"name": n, "description": description(n, {}), "inputSchema": _SCHEMAS[n]} for n in NAMES]


def _sheets(value):
    if value is None:
        return {}
    if not isinstance(value, list):
        raise ValueError("'voices' must be a list of voice sheet objects")
    out = {}
    for i, sheet in enumerate(value):
        sheet = dialogue_sheet._check_types(sheet, f"voices[{i}]")
        for name in [sheet["name"]] + list(sheet.get("aliases") or []):
            out[name.upper()] = sheet
    return out


def _check(args):
    text = args.get("text")
    if not isinstance(text, str):
        raise ValueError("'text' is required and must be a string")
    fmt = args.get("format") or "auto"
    records = dialogue_parse.parse(text, "<text>", None if fmt == "auto" else fmt)
    themes = args.get("theme_words")
    if themes is not None and not (isinstance(themes, list) and all(isinstance(t, str)
                                                                     for t in themes)):
        raise ValueError("'theme_words' must be a list of strings")
    report = dialogue.audit(records, _sheets(args.get("voices")), {},
                            min_lines=args.get("min_lines") or 20, theme_words=themes or [])
    report["gate"] = dialogue.gate(report)
    report["worst"] = dialogue.worst(report, int(args.get("worst", 30)))
    report["summary"] = dialogue.summary_table(report)
    report["detail"] = [d for d in report["detail"] if d["findings"]]
    return report


_HANDLERS = {"dialogue_check": _check}


def handle(name, args):
    return _HANDLERS[name](args)
