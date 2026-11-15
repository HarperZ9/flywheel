"""MCP tool definitions and handlers for the house voice.

house_brief returns the brief a model reads at session start. house_transform
runs the deterministic house transform on text the host passes and returns
the text, located notes and a house receipt. Both are local and read-only: they
read the packaged spec and the house settings file and write nothing.
"""
from . import house, house_settings
from .tool_text import description

NAMES = ("house_brief", "house_transform")
_SETTINGS = {"type": "object", "description": "mode and tuning keys for this call only, "
             "for example {\"length\": \"terse\"}; omitted keys come from your settings"}
_SCHEMAS = {
    "house_brief": {"type": "object", "properties": {"settings": _SETTINGS}},
    "house_transform": {"type": "object", "required": ["text"], "properties": {
        "text": {"type": "string", "description": "model output to transform"},
        "settings": _SETTINGS,
        "house": {"type": "boolean", "default": True,
                  "description": "false returns the text unchanged with a receipt saying so"}}},
}
TOOLS = [{"name": n, "description": description(n, {}), "inputSchema": _SCHEMAS[n]} for n in NAMES]


def _settings(args):
    overrides = args.get("settings")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("'settings' must be an object")
    if args.get("house") is False:
        overrides = dict(overrides or {}, mode="off")
    elif "house" in args and not isinstance(args["house"], bool):
        raise ValueError("'house' must be true or false")
    return house_settings.for_request(overrides=overrides)


def _brief(args):
    s = _settings(args)
    return {"brief": house.brief(s), "version": house.spec()["version"],
            "fingerprint": house.fingerprint(s), "mode": s["mode"]}


def _transform(args):
    text = args.get("text")
    if not isinstance(text, str):
        raise ValueError("'text' is required and must be a string")
    return house.transform(text, _settings(args))


_HANDLERS = {"house_brief": _brief, "house_transform": _transform}


def handle(name, args):
    return _HANDLERS[name](args)
