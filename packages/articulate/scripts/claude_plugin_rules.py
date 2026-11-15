"""Checks a built Articulate Writing plugin folder against the rules it ships under.

Each check returns a list of problems, empty when the folder passes. The rules
come from Claude's plugin pre-submission checklist and manifest reference, read
on 2026-09-27: file limits that hold a version for review, names that stop
validation, the manifest fields the directory reads, a README of at least 40
words with a privacy policy, and skill front matter. One more rule is this
repository's own: no file named or shaped like a credential. A clean result here does
not predict the directory's own validation, which runs more checks.

Standard library only, so it runs wherever the build runs.
"""
import json
import re
import stat
import urllib.parse
from pathlib import Path

MAX_FILES = 512
MAX_BYTES = 256 * 1024
NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
DEVICE = re.compile(r"(?i)^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$")
JUNK = {".ds_store", "thumbs.db", "desktop.ini", "__macosx"}
POLICY_TOPICS = ("Data collected", "Use and storage", "Third-party sharing", "Retention",
                 "Contact")
LICENSE_ID = "FSL-1.1-MIT"
# The directory reads these from the Claude manifest only; Claude Code ignores them,
# so they stay out of the portable and Codex manifests.
LISTING_URLS = ("documentationUrl", "supportUrl", "privacyPolicyUrl", "termsOfServiceUrl")
LISTING_KEYS = ("displayName", "metadata", "icon") + LISTING_URLS
# Complete images the directory accepts as plugin files; exempt from the text and
# 256 KiB rules. The icon must be a square PNG or JPEG of 512 to 2048 px under 2 MB.
IMAGE_MAGIC = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
ICON_MAX_BYTES = 2 * 1024 * 1024
SERVER_FILE = "${CLAUDE_PLUGIN_ROOT}/server/serve.py"
HOOK_FILE = "${CLAUDE_PLUGIN_ROOT}/server/edit_hook.py"
HOUSE_HOOK_FILE = "${CLAUDE_PLUGIN_ROOT}/server/house_hook.py"
HOOKS_FILE = "./hooks/hooks.json"
# The hooks the plugin declares, all with the same isolated interpreter flags as
# the server: the house-voice brief at session start, the advisory check after a
# file write or edit, and the house-voice Stop check, which does nothing unless
# the user chose mode revise. Exact comparison rejects another hook, another
# event, a blocking PreToolUse entry or a changed command.
_HOUSE = 'python3 -I -S -B -X utf8 "%s"' % HOUSE_HOOK_FILE
EXPECTED_HOOKS = {
    "SessionStart": [{"matcher": "startup|resume|clear|compact",
                      "hooks": [{"type": "command", "timeout": 10, "command": _HOUSE}]}],
    "PostToolUse": [{"matcher": "Write|Edit|MultiEdit|apply_patch",
                     "hooks": [{"type": "command", "timeout": 15,
                                "command": 'python3 -I -S -B -X utf8 "%s"' % HOOK_FILE}]}],
    "Stop": [{"hooks": [{"type": "command", "timeout": 15, "command": _HOUSE}]}]}
PUBLIC_TEXT = (".md", ".json")
EM_DASH = "—"
LOCAL_PATH = re.compile(r"\b[A-Za-z]:[\\/]|/Users/|/home/[a-z]")
# A file named like a credential store, or text shaped like a key or token. The
# build copies only tracked files; this catches one that was committed.
SECRET_NAME = re.compile(r"(?i)^(?:\.env(?!\.example$)(?:\..*)?|.*\.(?:pem|key|p12|pfx|jks)"
                         r"|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|\.netrc|\.npmrc|\.pypirc)$")
SECRET_TEXT = re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{20,}"
                         r"|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}"
                         r"|xox[abprs]-[A-Za-z0-9-]{10,}|-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")


def _json(root, rel, problems):
    try:
        return json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems.append(f"{rel}: cannot be read as JSON ({exc})")
        return None


def bundled_version(root):
    text = (root / "src" / "articulate" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return found.group(1) if found else None


def check_manifest(root):
    problems = []
    m = _json(root, ".claude-plugin/plugin.json", problems)
    if m is None:
        return problems
    if not NAME.match(m.get("name", "")):
        problems.append("plugin.json: name must be lowercase letters, digits and hyphens")
    for key in ("displayName", "version", "description", "homepage", "repository"):
        if not isinstance(m.get(key), str) or not m[key].strip():
            problems.append(f"plugin.json: {key} is missing")
    if not (m.get("author") or {}).get("name"):
        problems.append("plugin.json: author.name is missing")
    if m.get("license") != LICENSE_ID:
        problems.append(f"plugin.json: license must be {LICENSE_ID}")
    for key in ("homepage",) + LISTING_URLS:
        url = urllib.parse.urlparse(m.get(key) or "")
        if url.scheme != "https" or not url.netloc:
            problems.append(f"plugin.json: {key} must be an https URL")
    problems += _check_icon(root, m.get("icon"))
    if m.get("version") != bundled_version(root):
        problems.append("plugin.json: version differs from the bundled package version")
    problems += _check_marketplace(root, m.get("name"))
    return problems


def png_size(data):
    """(width, height) of a PNG, or None when data is not a PNG."""
    if data[:8] != IMAGE_MAGIC[".png"] or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _check_icon(root, icon):
    if not isinstance(icon, str) or not icon.startswith("./"):
        return ["plugin.json: icon must be a ./ path to an image in the plugin"]
    path = root / icon[2:]
    if not path.is_file():
        return [f"plugin.json: icon {icon} is missing"]
    data = path.read_bytes()
    size = png_size(data)
    if size is None or size[0] != size[1] or not 512 <= size[0] <= 2048:
        return ["plugin.json: icon must be a square PNG of 512 to 2048 px"]
    if len(data) >= ICON_MAX_BYTES:
        return ["plugin.json: icon must be under 2 MB"]
    return []


def _check_marketplace(root, plugin_name):
    problems = []
    mk = _json(root, ".claude-plugin/marketplace.json", problems)
    if mk is None:
        return problems
    if not mk.get("name") or not (mk.get("owner") or {}).get("name"):
        problems.append("marketplace.json: name and owner.name are required")
    if not mk.get("description"):
        problems.append("marketplace.json: description is missing")
    entries = mk.get("plugins") or []
    if [(e.get("name"), e.get("source")) for e in entries] != [(plugin_name, "./")]:
        problems.append("marketplace.json: one entry naming this plugin with source ./")
    if any("version" in e for e in entries):
        problems.append("marketplace.json: version belongs in plugin.json only")
    return problems


def check_server(root):
    problems = []
    cfg = _json(root, ".mcp.json", problems)
    if cfg is None:
        return problems
    servers = cfg.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        return problems + [".mcp.json: needs a top-level mcpServers object"]
    for name, entry in servers.items():
        args = entry.get("args") or []
        if entry.get("command") != "python3":
            problems.append(f".mcp.json {name}: command must be python3")
        if [a for a in args if "${" in a] != [SERVER_FILE]:
            problems.append(f".mcp.json {name}: the only variable must be {SERVER_FILE}")
        if not all(isinstance(v, str) and "${" not in v
                   for v in (entry.get("env") or {}).values()):
            problems.append(f".mcp.json {name}: env values must be plain strings")
    if not (root / "server" / "serve.py").is_file():
        problems.append("server/serve.py is missing")
    return problems


def check_portable(root):
    """Check our fixed local bundle profile, including compatibility parity.

    This is deliberately narrower than general Agent Plugins schema validation.
    Portable components are canonical; the Codex overlay is a fallback only.
    """
    problems = []
    paths = ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
             "mcp.json", ".mcp.json", ".codex-mcp.json")
    portable, claude, codex, mcp, legacy, codex_mcp = [
        _json(root, path, problems) for path in paths]
    if any(not isinstance(d, dict) for d in (portable, claude, codex, mcp, legacy, codex_mcp)):
        return problems + ["portable plugin: manifests must be objects"]
    identity = {k: v for k, v in claude.items() if k not in LISTING_KEYS}
    extension = portable.get("extensions", {}).get("com.openai", {})
    interface = extension.get("interface")
    expected = {"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
                **identity, "extensions": {"com.openai": {"interface": interface}}}
    if portable != expected:
        problems.append("plugin.json: portable identity or schema differs from the Claude manifest")
    if not isinstance(interface, dict) or not interface.get("displayName"):
        problems.append("plugin.json: OpenAI interface is missing")
    expected_codex = {**identity, "skills": "./skills/",
                      "mcpServers": "./.codex-mcp.json", "hooks": HOOKS_FILE,
                      "interface": interface}
    if codex != expected_codex:
        problems.append(".codex-plugin/plugin.json: identity or OpenAI settings drift")
    # Derive both launch forms from the preserved Claude configuration. Exact
    # comparison also rejects extra transports, environment settings and servers.
    expected_server = {
        "command": "python3",
        "args": ["-I", "-S", "-B", "-X", "utf8", SERVER_FILE],
        "env": {"ARTICULATE_MCP_TOOLS": "local", "ARTICULATE_LOCAL_ONLY": "1"},
    }
    if legacy != {"mcpServers": {"articulate": expected_server}}:
        problems.append(".mcp.json: launch differs from the isolated local-only profile")
    portable_server = {**expected_server, "type": "stdio",
                       "args": expected_server["args"][:-1] + ["${PLUGIN_ROOT}/server/serve.py"]}
    if mcp != {"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
               "mcpServers": {"articulate": portable_server}}:
        problems.append("mcp.json: portable stdio launch differs from the local-only profile")
    compat_server = {**expected_server, "cwd": ".",
                     "args": expected_server["args"][:-1] + ["server/serve.py"]}
    if codex_mcp != {"mcpServers": {"articulate": compat_server}}:
        problems.append(".codex-mcp.json: compatibility launch differs from the local-only profile")
    return problems


def check_hooks(root):
    """The plugin's hooks file declares exactly the house-voice and edit-time hooks."""
    problems = []
    cfg = _json(root, "hooks/hooks.json", problems)
    if cfg is None:
        return problems
    if not isinstance(cfg.get("description"), str) or not cfg["description"].strip():
        problems.append("hooks/hooks.json: description is missing")
    if cfg.get("hooks") != EXPECTED_HOOKS or set(cfg) - {"description", "hooks"}:
        problems.append("hooks/hooks.json: differs from the declared SessionStart, advisory "
                        "PostToolUse and Stop hooks")
    for script in ("edit_hook.py", "house_hook.py"):
        if not (root / "server" / script).is_file():
            problems.append(f"server/{script} is missing")
    return problems


def _names_ok(rel):
    problems = []
    for part in rel.parts:
        if not part.isascii():
            problems.append(f"{rel}: non-ASCII name")
        if ":" in part or part.endswith((".", " ")) or DEVICE.match(part):
            problems.append(f"{rel}: name is not valid on Windows")
        if part.lower() in JUNK or part == "__pycache__":
            problems.append(f"{rel}: system or cache file")
    return problems


def contained_entries(root):
    """Walk without following links or Windows reparse points, before reads.

    This rejects existing escape paths; callers must keep the input directory
    stable during validation and packaging. It is not a concurrent-write lock.
    """
    root = Path(root)
    entries, pending = [], [root]
    boundary = root.resolve()
    while pending:
        path = pending.pop()
        info = path.lstat()
        label = path.relative_to(root) if path != root else Path(".")
        if (stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError(f"{label}: symbolic link or reparse entry is not allowed")
        resolved = path.resolve()
        if resolved != boundary and boundary not in resolved.parents:
            raise ValueError(f"{label}: entry resolves outside the plugin")
        if path != root:
            entries.append(path)
        if stat.S_ISDIR(info.st_mode):
            pending.extend(p for p in path.iterdir() if p.name != ".git")
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{label}: non-regular entry is not allowed")
    return sorted(entries)


def check_files(root):
    problems, seen = [], {}
    try:
        files = contained_entries(root)
    except (ValueError, OSError) as exc:
        return [str(exc)]
    for path in files:
        rel = path.relative_to(root)
        problems += _names_ok(rel)
        key = str(rel).lower()
        if key in seen:
            problems.append(f"{rel}: differs from {seen[key]} only by case")
        seen[key] = rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        magic = IMAGE_MAGIC.get(path.suffix.lower())
        if magic is not None:
            if not data.startswith(magic):
                problems.append(f"{rel}: not a complete {path.suffix} image")
            continue
        if len(data) >= MAX_BYTES:
            problems.append(f"{rel}: {len(data)} bytes, at or over 256 KiB")
        if b"\0" in data or not _utf8(data):
            problems.append(f"{rel}: not a text file")
        if SECRET_NAME.match(path.name):
            problems.append(f"{rel}: named like a credential file")
        elif SECRET_TEXT.search(data.decode("utf-8", "replace")):
            problems.append(f"{rel}: holds text shaped like a credential")
        if path.suffix in (".mcpb", ".dxt", ".pyc", ".pyo", ".pyd"):
            problems.append(f"{rel}: bundle or compiled file")
    count = sum(1 for p in files if p.is_file())
    if count > MAX_FILES:
        problems.append(f"{count} files, over {MAX_FILES}")
    for banned in ("bin", "CLAUDE.md", ".gitattributes"):
        if (root / banned).exists():
            problems.append(f"{banned} must not be at the plugin root")
    return problems


def _utf8(data):
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def policy_section(readme_text):
    """The body of the README's Privacy Policy section, or None."""
    parts = readme_text.split("\n## Privacy Policy\n", 1)
    return parts[1].split("\n## ", 1)[0].strip("\n") if len(parts) == 2 else None


def check_docs(root):
    problems = []
    readme = (root / "README.md").read_text(encoding="utf-8")
    prose = re.sub(r"```.*?```", " ", readme, flags=re.DOTALL)
    if len(prose.split()) < 40:
        problems.append("README.md: fewer than 40 words outside code blocks")
    policy = policy_section(readme)
    if policy is None:
        return problems + ["README.md: no section titled Privacy Policy"]
    problems += [f"README.md: the privacy policy does not cover {t}"
                 for t in POLICY_TOPICS if f"**{t}.**" not in policy]
    privacy = (root / "PRIVACY.md").read_text(encoding="utf-8")
    if privacy != "# Privacy Policy\n\n" + policy + "\n":
        problems.append("PRIVACY.md differs from the README's Privacy Policy section")
    for path in contained_entries(root):
        rel = path.relative_to(root)
        if path.suffix in PUBLIC_TEXT and rel.parts[0] != "src" and path.is_file():
            text = path.read_text(encoding="utf-8")
            if EM_DASH in text:
                problems.append(f"{rel}: em dash in public text")
            if re.search(r"(?i)\bopen[- ]source\b", text):
                problems.append(f"{rel}: says open source; the license is source-available")
            if LOCAL_PATH.search(text):
                problems.append(f"{rel}: local file path in public text")
    return problems


def skill_front_matter(text):
    """The front matter of a SKILL.md as a dict of one-line keys, or None."""
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return None
    block = text[4:text.index("\n---\n", 4)]
    fields = {}
    for line in block.splitlines():
        key, sep, value = line.partition(": ")
        if not sep or not re.fullmatch(r"[a-z-]+", key):
            return None
        fields[key] = value.strip()
    return fields


def check_skills(root, plugin_name):
    problems = []
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    if not skills:
        problems.append("skills: no SKILL.md found")
    for path in skills:
        rel = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        fm = skill_front_matter(text)
        if fm is None:
            problems.append(f"{rel}: front matter is missing or not simple key: value lines")
            continue
        if fm.get("name") != path.parent.name or not NAME.match(fm.get("name", "")):
            problems.append(f"{rel}: name must equal the folder name")
        if not 0 < len(fm.get("description", "")) <= 1024:
            problems.append(f"{rel}: description must be 1 to 1,024 characters")
        if len(text.splitlines()) >= 500:
            problems.append(f"{rel}: 500 lines or more")
        prefix = "mcp__plugin_%s_" % plugin_name
        tools = [t.strip() for t in fm.get("allowed-tools", "").split(",") if t.strip()]
        problems += [f"{rel}: allowed tool {t} is not one of this plugin's tools"
                     for t in tools if not t.startswith(prefix)]
    return problems


def check_bundle(root):
    """Every problem found in the built plugin folder at root."""
    root = Path(root)
    # Check the entire tree before any manifest, documentation or source read.
    try:
        contained_entries(root)
    except (ValueError, OSError) as exc:
        return [str(exc)]
    problems = (check_files(root) + check_manifest(root) + check_server(root)
                + check_portable(root) + check_hooks(root))
    if (root / "README.md").is_file() and (root / "PRIVACY.md").is_file():
        problems += check_docs(root)
    else:
        problems.append("README.md and PRIVACY.md are required")
    name = (json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
            .get("name", "") if (root / ".claude-plugin" / "plugin.json").is_file() else "")
    return problems + check_skills(root, name)
