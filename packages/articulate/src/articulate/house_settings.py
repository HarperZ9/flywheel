"""Settings for the house voice: mode and tuning, from defaults, the settings
file and the environment, in that order.

Modes: off; brief (session-start brief only); default (brief plus the advisory
file notes); revise (default plus one revision request when a reply breaks a
banned rule or claims a human life). The house voice is off until the user
turns it on (DEFAULT_MODE). An explicit request, such as `articulate house
apply` or the house_transform tool, is itself the opt-in: with no mode set by
the user it runs in mode default (for_request). A mode the user set, off
included, always wins.

The settings file is <config>/articulate/house.json: %APPDATA% on Windows,
$XDG_CONFIG_HOME (default ~/.config) elsewhere, or ARTICULATE_CONFIG_DIR when
set. Only the command line writes it. Hooks and MCP tools read it and never
write. Environment variables win over the file: ARTICULATE_HOUSE_VOICE for the
mode, ARTICULATE_HOUSE_<KEY> for a tuning key.

The banned tics and the identity rules are not tunable. A voice that may claim
a human life, or keep its sycophantic openers, is a different voice.
"""
import json
import os
import pathlib
import tempfile

from .house_spec import default_tuning, spec

MODES = ("off", "brief", "default", "revise")
# Off by default since 0.8.0's re-measure: a blinded reader preferred replies
# written without the brief (see CHANGELOG). The user turns it on.
DEFAULT_MODE = "off"
_OFF = ("off", "0", "false", "no", "none")
_ON = ("on", "1", "true", "yes")
TUNING = {key: tuple(entry["values"]) for key, entry in spec()["tuning"].items()}


def config_dir(environ=None):
    env = os.environ if environ is None else environ
    if env.get("ARTICULATE_CONFIG_DIR"):
        return pathlib.Path(env["ARTICULATE_CONFIG_DIR"])
    if os.name == "nt":
        base = env.get("APPDATA") or str(pathlib.Path.home() / "AppData" / "Roaming")
    else:
        base = env.get("XDG_CONFIG_HOME") or str(pathlib.Path.home() / ".config")
    return pathlib.Path(base) / "articulate"


def settings_path(environ=None):
    return config_dir(environ) / "house.json"


def normalize_mode(value):
    v = str(value).strip().lower()
    if v in _OFF:
        return "off"
    if v in _ON:
        return "default"
    if v in MODES:
        return v
    raise ValueError("house voice mode must be one of %s, on or off" % ", ".join(MODES))


def validate(settings):
    """A clean {mode, tuning} dict, or ValueError naming the first bad key."""
    if not isinstance(settings, dict):
        raise ValueError("house settings must be an object")
    unknown = set(settings) - {"mode", "tuning"}
    if unknown:
        raise ValueError("unknown house setting: %s" % sorted(unknown)[0])
    out = {"mode": normalize_mode(settings.get("mode", "default")), "tuning": {}}
    tuning = settings.get("tuning", {})
    if not isinstance(tuning, dict):
        raise ValueError("house tuning must be an object")
    for key, value in tuning.items():
        if key not in TUNING:
            raise ValueError("%s is not a tuning key; tunable keys are %s"
                             % (key, ", ".join(sorted(TUNING))))
        if value not in TUNING[key]:
            raise ValueError("%s must be one of %s" % (key, ", ".join(TUNING[key])))
        out["tuning"][key] = value
    return out


def _read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return validate(json.load(fh)), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        return None, "ignored %s: %s" % (path, exc)


def _split(overrides):
    """Flat overrides ({"length": "terse", "mode": "off"}) to {mode, tuning}."""
    overrides = dict(overrides or {})
    mode = overrides.pop("mode", None)
    nested = overrides.pop("tuning", {})
    if not isinstance(nested, dict):
        raise ValueError("house tuning must be an object")
    out = {"tuning": dict(nested, **overrides)}
    if mode is not None:
        out["mode"] = mode
    return validate(out) if mode is not None else dict(validate(out), mode=None)


def resolve(environ=None, overrides=None):
    """Active settings with the source of each value: default, file, env or call."""
    env = os.environ if environ is None else environ
    result = {"mode": DEFAULT_MODE, "tuning": default_tuning(), "problems": []}
    sources = {"mode": "default", **{k: "default" for k in TUNING}}
    stored, problem = _read_file(settings_path(env))
    if problem:
        result["problems"].append(problem)
    layers = [("file", stored)]
    try:
        layers.append(("env", _env_layer(env)))
    except ValueError as exc:
        result["problems"].append("ignored environment: %s" % exc)
    if overrides:
        layers.append(("call", _split(overrides)))
    for source, layer in layers:
        if not layer:
            continue
        if layer.get("mode") is not None:
            result["mode"], sources["mode"] = layer["mode"], source
        for key, value in layer.get("tuning", {}).items():
            result["tuning"][key], sources[key] = value, source
    result["sources"] = sources
    return result


def _env_layer(env):
    layer = {"mode": None, "tuning": {}}
    if env.get("ARTICULATE_HOUSE_VOICE", "").strip():
        layer["mode"] = normalize_mode(env["ARTICULATE_HOUSE_VOICE"])
    for key in TUNING:
        value = env.get("ARTICULATE_HOUSE_" + key.upper(), "").strip().lower()
        if value:
            if value not in TUNING[key]:
                raise ValueError("%s must be one of %s" % (key, ", ".join(TUNING[key])))
            layer["tuning"][key] = value
    return layer


def stored(environ=None):
    """The settings file's content, or an empty {mode: None, tuning: {}}."""
    found, _ = _read_file(settings_path(environ))
    return found or {"mode": None, "tuning": {}}


def save(settings, environ=None):
    """Write the settings file atomically. Only the command line calls this."""
    clean = validate({k: v for k, v in settings.items() if v is not None})
    path = settings_path(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".house-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(clean, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def for_request(environ=None, overrides=None):
    """Settings for an explicit request to apply the voice or show the brief.
    The request is the opt-in, so a mode left at the built-in default becomes
    mode default; a mode from the file, the environment or the call stays."""
    result = resolve(environ, overrides)
    if result["sources"]["mode"] == "default":
        result["mode"], result["sources"]["mode"] = "default", "request"
    return result
