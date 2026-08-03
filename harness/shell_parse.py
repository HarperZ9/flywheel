"""shell_parse.py -- parse a shell command into typed capability findings.

Split out of shell_admission.py at the 300-line gate. The boundary is real: this
module turns a command STRING into a list of Findings (what capabilities appear,
and where in the command tree), while shell_admission.py turns findings into an
admission DECISION. Either can be replaced without touching the other.

Quote-aware, substitution-descending, fail-closed. The three properties a regex
over the raw string cannot provide; see shell_admission.py for why they matter.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass

from .receipt_fields import _NominalEnum


class Capability(_NominalEnum):
    """What a command is able to do. A closed, unordered vocabulary."""
    BENIGN = "benign"
    UNKNOWN = "unknown"
    NETWORK_EGRESS = "network_egress"
    DESTRUCTIVE_FS = "destructive_fs"
    CREDENTIAL_ACCESS = "credential_access"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DEVICE_WRITE = "device_write"
    CODE_DOWNLOAD_EXEC = "code_download_exec"
    PACKAGE_PUBLISH = "package_publish"
    PROCESS_CONTROL = "process_control"
    HISTORY_TAMPER = "history_tamper"


class AdmissionError(ValueError):
    """A command that could not be parsed, so it cannot be admitted."""


@dataclass(frozen=True)
class Finding:
    """One classified sub-command in the parsed command tree."""
    capability: Capability
    executable: str
    depth: int          # 0 = top level, 1 = inside a substitution, etc.
    substitution: bool  # did this come from $(...) / backtick / <(...)?

    def to_dict(self) -> dict:
        return {"capability": self.capability.value, "executable": self.executable,
                "depth": self.depth, "substitution": self.substitution}


# Executable basename -> capability. Curated, not exhaustive.
_CAP: dict[str, Capability] = {}
for _name in ("curl", "wget", "nc", "ncat", "netcat", "telnet", "ssh", "scp",
              "sftp", "ftp", "rsync", "socat", "invoke-webrequest", "iwr",
              "invoke-restmethod", "irm"):
    _CAP[_name] = Capability.NETWORK_EGRESS
for _name in ("rm", "rmdir", "shred", "unlink", "srm"):
    _CAP[_name] = Capability.DESTRUCTIVE_FS
for _name in ("sudo", "su", "doas", "runas", "pkexec"):
    _CAP[_name] = Capability.PRIVILEGE_ESCALATION
for _name in ("mkfs", "fdisk", "parted", "diskpart"):
    _CAP[_name] = Capability.DEVICE_WRITE
for _name in ("kill", "killall", "pkill", "taskkill", "shutdown", "reboot",
              "halt", "poweroff"):
    _CAP[_name] = Capability.PROCESS_CONTROL
for _name in ("twine",):
    _CAP[_name] = Capability.PACKAGE_PUBLISH

_INTERPRETERS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish", "python",
                           "python3", "python2", "perl", "ruby", "node", "php",
                           "pwsh", "powershell", "iex", "eval"})
_WRAPPERS = frozenset({"command", "nohup", "time", "nice", "stdbuf", "env",
                       "exec", "xargs", "then", "do", "else"})
_CRED_HINTS = ("/.ssh/", "id_rsa", "id_ed25519", "/.aws/credentials",
               "/.aws/config", ".env", "/.netrc", "/.docker/config",
               "/.kube/config", "credentials.json", "secrets.")
_SUBCMD_CAP = {
    ("npm", "publish"): Capability.PACKAGE_PUBLISH,
    ("yarn", "publish"): Capability.PACKAGE_PUBLISH,
    ("pnpm", "publish"): Capability.PACKAGE_PUBLISH,
    ("cargo", "publish"): Capability.PACKAGE_PUBLISH,
    ("gem", "push"): Capability.PACKAGE_PUBLISH,
    ("pip", "upload"): Capability.PACKAGE_PUBLISH,
    ("gh", "release"): Capability.PACKAGE_PUBLISH,
    ("docker", "push"): Capability.PACKAGE_PUBLISH,
    ("git", "push"): Capability.BENIGN,
}


def _split_substitutions(cmd: str) -> tuple[str, list[str]]:
    """Return (outer command with substitutions blanked, [inner command strings]).

    $(...) and backticks are active INSIDE double quotes, as in a real shell, so
    they are still descended there; single quotes are literal. Process
    substitution <(...) / >(...) is not active in double quotes. Raises on an
    unbalanced construct so the caller can fail closed.
    """
    inners: list[str] = []
    out: list[str] = []
    i, n = 0, len(cmd)
    in_single = False
    in_double = False
    while i < n:
        c = cmd[i]
        if in_single:
            out.append(c)
            if c == "'":
                in_single = False
            i += 1
            continue
        if c == "'" and not in_double:
            in_single = True
            out.append(c)
            i += 1
            continue
        if c == '"':
            in_double = not in_double
            out.append(c)
            i += 1
            continue
        if (c == "$" and i + 1 < n and cmd[i + 1] == "(") or \
           (c in "<>" and not in_double and i + 1 < n and cmd[i + 1] == "("):
            start = i + 2
            depth = 1
            j = start
            iq = ""
            while j < n and depth:
                cj = cmd[j]
                if iq:
                    if cj == iq:
                        iq = ""
                elif cj in "'\"":
                    iq = cj
                elif cj == "(":
                    depth += 1
                elif cj == ")":
                    depth -= 1
                j += 1
            if depth:
                raise AdmissionError("unbalanced command substitution")
            inners.append(cmd[start:j - 1])
            out.append(" ")
            i = j
            continue
        if c == "`":
            j = cmd.find("`", i + 1)
            if j == -1:
                raise AdmissionError("unbalanced backtick substitution")
            inners.append(cmd[i + 1:j])
            out.append(" ")
            i = j + 1
            continue
        out.append(c)
        i += 1
    if in_single or in_double:
        raise AdmissionError("unbalanced quote")
    return "".join(out), inners


def _segments(cmd: str) -> list[str]:
    """Split a command on top-level pipeline/list operators, quote-aware."""
    segs: list[str] = []
    buf: list[str] = []
    i, n = 0, len(cmd)
    quote = ""
    while i < n:
        c = cmd[i]
        if quote:
            buf.append(c)
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in "'\"":
            quote = c
            buf.append(c)
            i += 1
            continue
        if cmd[i:i + 2] in ("&&", "||"):
            segs.append("".join(buf)); buf = []; i += 2; continue
        if c in ";|&\n":
            segs.append("".join(buf)); buf = []; i += 1; continue
        buf.append(c)
        i += 1
    segs.append("".join(buf))
    return [s for s in (s.strip() for s in segs) if s]


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError as e:
        raise AdmissionError(f"unparseable segment: {e}") from e


def _basename(word: str) -> str:
    return word.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _classify_segment(segment: str, depth: int, sub: bool,
                      findings: list[Finding]) -> None:
    words = _words(segment)
    idx = 0
    while idx < len(words):
        w = words[idx]
        if "=" in w and not w.startswith("=") and "/" not in w.split("=", 1)[0]:
            idx += 1
            continue
        if _basename(w) in _WRAPPERS:
            idx += 1
            continue
        break
    if idx >= len(words):
        return
    exe = _basename(words[idx])
    rest = words[idx + 1:]

    for w in words:
        wl = w.lower()
        if any(h in wl for h in _CRED_HINTS):
            findings.append(Finding(Capability.CREDENTIAL_ACCESS, exe, depth, sub))
            break

    if exe == "dd" and any(a.startswith("of=") and a[3:].startswith("/dev")
                           for a in rest):
        findings.append(Finding(Capability.DEVICE_WRITE, exe, depth, sub))
        return
    if any(w.startswith("/dev/") for w in rest) and exe in ("cp", "mv", "tee"):
        findings.append(Finding(Capability.DEVICE_WRITE, exe, depth, sub))

    if exe in _INTERPRETERS and (not rest or any(
            a in ("-c", "-e", "-command", "--command") for a in rest)):
        findings.append(Finding(Capability.CODE_DOWNLOAD_EXEC, exe, depth, sub))
        return

    if rest:
        sc = _SUBCMD_CAP.get((exe, _basename(rest[0])))
        if sc is not None and sc != Capability.BENIGN:
            findings.append(Finding(sc, exe, depth, sub))
            return
        if sc == Capability.BENIGN:
            return

    cap = _CAP.get(exe)
    findings.append(Finding(cap if cap is not None else Capability.UNKNOWN,
                            exe, depth, sub))


def _walk(cmd: str, depth: int, sub: bool, findings: list[Finding]) -> None:
    outer, inners = _split_substitutions(cmd)
    for seg in _segments(outer):
        _classify_segment(seg, depth, sub, findings)
    for inner in inners:
        _walk(inner, depth + 1, True, findings)


def walk_findings(cmd: str) -> list[Finding]:
    """Parse a command into capability findings. Raises AdmissionError on a
    construct that cannot be parsed, so the caller can fail closed."""
    findings: list[Finding] = []
    _walk(cmd, 0, False, findings)
    return findings
