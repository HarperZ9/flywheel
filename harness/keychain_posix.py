"""keychain_posix.py -- the system credential store on macOS and Linux.

Flywheel drives the store through the command-line tool the system ships:

  macOS   `security`      the login Keychain, service `flywheel`
  Linux   `secret-tool`   the Secret Service (GNOME Keyring, KWallet), from
                          the libsecret-tools package

When the tool is absent the answer is a refusal that names it. There is no
file fallback: a key is never written to a plain file here.

A secret is sent to the tool on standard input and never placed on a command
line, where another local user could read it from the process list. For
`security` that means its interactive mode, which reads one command per line;
a secret that the line format cannot carry (whitespace, quotes, a backslash)
is stored base64-encoded behind a marker and decoded when read.

These backends were written on Windows and tested with the subprocess call
replaced. They have not been run on macOS or Linux.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import sys

SERVICE = "flywheel"
TIMEOUT_SECONDS = 20
TOOLS = {"darwin": "security", "linux": "secret-tool"}
_INSTALL_HINT = {
    "security": "it ships with macOS; check that /usr/bin is on PATH",
    "secret-tool": "install libsecret-tools (Debian, Ubuntu) or libsecret "
                   "(Fedora, Arch) and run a Secret Service such as GNOME Keyring",
}
_UNSAFE_FOR_SECURITY = frozenset(" \t\r\n\"'\\")
_ENCODED = "fwb64:"


def _line_safe(secret: str) -> str:
    """The secret as one token `security -i` reads unchanged."""
    plain = secret.isascii() and not _UNSAFE_FOR_SECURITY & frozenset(secret)
    if plain and not secret.startswith(_ENCODED):
        return secret
    return _ENCODED + base64.urlsafe_b64encode(secret.encode("utf-8")).decode("ascii")


def _decoded(value: str) -> "str | None":
    if not value.startswith(_ENCODED):
        return value
    try:
        return base64.urlsafe_b64decode(value[len(_ENCODED):]).decode("utf-8")
    except ValueError:
        return None                    # not something this module wrote


def tool_name(platform: "str | None" = None) -> "str | None":
    platform = sys.platform if platform is None else platform
    return next((tool for prefix, tool in TOOLS.items()
                 if platform.startswith(prefix)), None)


def available(platform: "str | None" = None, which=shutil.which) -> bool:
    tool = tool_name(platform)
    return bool(tool and which(tool))


def refusal(platform: "str | None" = None, which=shutil.which) -> str:
    """Why no store can be used, in one sentence; '' when one can."""
    tool = tool_name(platform)
    if tool is None:
        return "no supported OS credential store on this platform"
    if which(tool):
        return ""
    return (f"the credential store needs the `{tool}` command, which was not "
            f"found: {_INSTALL_HINT[tool]}")


def _run(argv: list, stdin: "str | None", run) -> "subprocess.CompletedProcess":
    return run(argv, input=stdin, capture_output=True, text=True,
               timeout=TIMEOUT_SECONDS, check=False)


def _failure(tool: str, exc: Exception) -> dict:
    # The exception text can quote argv or input, so only its type is reported.
    return {"error": f"`{tool}` could not be run ({type(exc).__name__})"}


def read(name: str, platform=None, run=subprocess.run) -> "str | None":
    """The stored secret, or None when the store has none or cannot be asked."""
    tool = tool_name(platform)
    if tool == "security":
        argv = [tool, "find-generic-password", "-s", SERVICE, "-a", name, "-w"]
    elif tool == "secret-tool":
        argv = [tool, "lookup", "service", SERVICE, "account", name]
    else:
        return None
    try:
        done = _run(argv, None, run)
    except (OSError, subprocess.SubprocessError):
        return None                    # an absent or stuck tool holds no key
    value = (done.stdout or "").rstrip("\r\n")
    if done.returncode != 0 or not value:
        return None
    return _decoded(value) if tool == "security" else value


def write(name: str, secret: str, platform=None, run=subprocess.run) -> dict:
    tool = tool_name(platform)
    if tool == "security":
        if _UNSAFE_FOR_SECURITY & frozenset(name) or not name.isascii():
            return {"error": "the macOS store cannot take a credential name that "
                             "contains whitespace, quotes or a backslash"}
        argv = [tool, "-i"]
        stdin = (f"add-generic-password -U -s {SERVICE} -a {name} "
                 f"-w {_line_safe(secret)}" + "\n")
    elif tool == "secret-tool":
        argv = [tool, "store", f"--label=Flywheel {name}",
                "service", SERVICE, "account", name]
        stdin = secret
    else:
        return {"error": refusal(platform)}
    try:
        done = _run(argv, stdin, run)
    except (OSError, subprocess.SubprocessError) as exc:
        return _failure(tool, exc)
    if done.returncode != 0:
        return {"error": f"credential store write failed (`{tool}` exit {done.returncode})"}
    # `security -i` can exit 0 after a failed line, so the write is read back.
    if tool == "security" and read(name, platform, run) != secret:
        return {"error": "credential store write failed (the key did not read back)"}
    return {"stored": name}


def remove(name: str, platform=None, run=subprocess.run) -> dict:
    tool = tool_name(platform)
    if tool == "security":
        argv = [tool, "delete-generic-password", "-s", SERVICE, "-a", name]
    elif tool == "secret-tool":
        if read(name, platform, run) is None:   # `clear` exits 0 for a missing item
            return {"error": f"no stored credential named '{name}'"}
        argv = [tool, "clear", "service", SERVICE, "account", name]
    else:
        return {"error": refusal(platform)}
    try:
        done = _run(argv, None, run)
    except (OSError, subprocess.SubprocessError) as exc:
        return _failure(tool, exc)
    if done.returncode != 0:
        return {"error": f"no stored credential named '{name}'"}
    return {"deleted": name}
