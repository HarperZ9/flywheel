"""shell_ops.py -- split a shell command into simple operations. Parse only.

`rm -rf backups && echo done > log.txt` becomes two ops: rm with flags
{r, f} and the argument `backups`; echo with a write redirect to `log.txt`.
Command substitutions are parsed as further ops, so `echo $(rm -rf x)` still
shows the rm. Nothing here runs a command. An unparseable command returns one
op with verb "<unparseable>".
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

_SUBST = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
_SEPARATORS = {";", "&&", "||", "|", "&", "\n", "(", ")"}
_WRAPPERS = {"sudo", "nohup", "env", "time", "nice", "xargs", "exec", "command"}


@dataclass
class Op:
    verb: str
    flags: set = field(default_factory=set)
    args: list = field(default_factory=list)
    long: list = field(default_factory=list)
    redirect: tuple | None = None      # (">" or ">>", path)
    piped_from: str = ""               # verb of the op this one reads a pipe from
    raw: list = field(default_factory=list)


def _tokens(command: str) -> list[str] | None:
    lex = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:
        return None


def _segments(tokens: list[str]) -> list[tuple[list[str], str]]:
    """Split on separators; each segment carries the separator before it."""
    segs, cur, before = [], [], ""
    for tok in tokens:
        if tok in _SEPARATORS or set(tok) <= set(";&|()"):
            if cur:
                segs.append((cur, before))
            cur, before = [], tok
            continue
        cur.append(tok)
    if cur:
        segs.append((cur, before))
    return segs


def _build(words: list[str], before: str, prev_verb: str) -> Op | None:
    while words and (words[0] in _WRAPPERS or re.match(r"^\w+=", words[0])):
        words = words[1:]
        while words and words[0].startswith("-") and words[0] != "--":
            words = words[1:]
    if not words:
        return None
    op = Op(verb=words[0].rsplit("/", 1)[-1], raw=list(words),
            piped_from=prev_verb if before == "|" else "")
    rest = words[1:]
    i = 0
    while i < len(rest):
        w = rest[i]
        if w.isdigit() and i + 1 < len(rest) and rest[i + 1] in (">", ">>", ">&"):
            i += 1          # a file-descriptor number such as the 2 in 2>/dev/null
            continue
        if w in (">", ">>") and i + 1 < len(rest):
            op.redirect = (w, rest[i + 1])
            i += 2
            continue
        if w in ("<", ">&", "&>", "&>>", "<<") and i + 1 < len(rest):
            i += 2
            continue
        if w.startswith("--") and len(w) > 2:
            op.long.append(w)
        elif w.startswith("-") and len(w) > 1 and not w[1].isdigit():
            op.flags.update(w[1:])
            op.long.append(w)
        else:
            op.args.append(w)
        i += 1
    return op


def _merge_redirects(tokens: list[str]) -> list[str]:
    out: list[str] = []
    for tok in tokens:
        if tok == ">" and out and out[-1] == ">":
            out[-1] = ">>"
        else:
            out.append(tok)
    return out


def parse(command: str) -> list[Op]:
    """Return the simple operations in a command, substitutions included."""
    ops: list[Op] = []
    for m in _SUBST.finditer(command):
        ops.extend(parse(m.group(1) or m.group(2) or ""))
    tokens = _tokens(_SUBST.sub("SUBST", command))
    if tokens is None:
        return ops + [Op(verb="<unparseable>", raw=[command])]
    tokens = _merge_redirects(tokens)
    prev = ""
    for words, before in _segments(tokens):
        op = _build(words, before, prev)
        if op is not None:
            ops.append(op)
            prev = op.verb
    return ops
