"""The house voice spec, the brief made from it, and its fingerprint.

The current spec lives in data/house_voice_v2.json (house/2) and is published
as docs/house-voice.md. Earlier versions stay packaged, so a receipt made under
house/1 still verifies against the spec it names. The brief is the short form a
model reads at session start. It is built from the spec and the active settings
every time, so the spec, the brief and the fingerprint in a receipt cannot
drift apart.

This module reads one packaged file and imports no style rules, so the
SessionStart hook can load it at about the cost of starting Python.
"""
import hashlib
import json
import os

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SPEC_FILES = {"house/1": os.path.join(_DATA, "house_voice_v1.json"),
              "house/2": os.path.join(_DATA, "house_voice_v2.json")}
CURRENT = "house/2"
SPEC_FILE = SPEC_FILES[CURRENT]
BRIEF_CEILING = 1500
OFF_HINT = "Turn this off with ARTICULATE_HOUSE_VOICE=off or `articulate house off`."
_CACHE = {}


def versions():
    """Every spec version this install can verify, oldest first."""
    return list(SPEC_FILES)


def spec(version=None):
    """The parsed spec for version (the current one by default). Callers get a
    fresh copy, so no caller can change it."""
    version = version or CURRENT
    if version not in SPEC_FILES:
        raise ValueError("unknown house voice version %r; this install has %s"
                         % (version, ", ".join(SPEC_FILES)))
    if version not in _CACHE:
        with open(SPEC_FILES[version], "r", encoding="utf-8") as fh:
            _CACHE[version] = json.loads(fh.read())
    return json.loads(json.dumps(_CACHE[version]))


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def default_tuning(version=None):
    return {key: entry["default"] for key, entry in spec(version)["tuning"].items()}


def _active(settings, version=None):
    """The parts of the settings that change what the voice asks for."""
    if settings is None:
        return {"mode": "default", "tuning": default_tuning(version)}
    return {"mode": settings["mode"], "tuning": dict(settings["tuning"])}


def fingerprint(settings=None, version=None):
    """SHA-256 of the canonical spec for version plus the active mode and tuning.
    Each version has its own fingerprint, since its spec differs."""
    body = canonical({"spec": spec(version), "active": _active(settings, version)})
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def brief(settings=None, version=None):
    """The brief text for the active tuning, one instruction per line."""
    s = spec(version)
    tuning = _active(settings, version)["tuning"]
    out = [s["brief"]["header"]]
    for line in s["brief"]["lines"]:
        if line.startswith("@"):
            key = line[1:]
            line = s["tuning"][key]["lines"][tuning.get(key, s["tuning"][key]["default"])]
        if line:
            out.append(line)
    return "\n".join(out)


def session_context(settings=None):
    """What the SessionStart hook hands the model: the brief, the spec version
    and fingerprint, and how to turn the voice off."""
    text = brief(settings)
    tail = "(%s, %s. %s)" % (spec()["version"], fingerprint(settings), OFF_HINT)
    return text + "\n" + tail
