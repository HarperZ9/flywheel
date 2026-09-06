"""scan_rules.py -- what the code scanner looks for, and how each rule is proved.

Every rule carries two source snippets it is checked against on each run: a
`probe` it must fire on and a `control` it must stay quiet on. A rule that
stops matching, because an AST shape changed under a new Python or because an
edit broke it, would otherwise keep contributing to a clean result. Clean and
broken read identically at the finding level, so the ruleset is measured
separately from the corpus and the verdicts are published side by side.

Matching is on the AST, never on the text. A regex scanner finds the word
`shell=True` inside a docstring that warns against it, and misses the call
split across two lines. Both mistakes cost trust in the same direction.

The set is small on purpose. Eight rules that fire on their probes and stay
quiet on their controls are worth more than eighty nobody has measured.
"""
from __future__ import annotations

import ast


def _dotted(node: ast.AST) -> str:
    """The dotted name of a call target, empty when it is not a plain name."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _keyword(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is(node, value) -> bool:
    return isinstance(node, ast.Constant) and node.value is value


def _calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node, _dotted(node.func)


def _shell_true(tree):
    return [(c.lineno, f"{name or 'call'}(shell=True)")
            for c, name in _calls(tree) if _is(_keyword(c, "shell"), True)]


def _eval_exec(tree):
    return [(c.lineno, f"{name}()") for c, name in _calls(tree)
            if name in ("eval", "exec")]


def _yaml_unsafe(tree):
    return [(c.lineno, "yaml.load without a Loader") for c, name in _calls(tree)
            if name == "yaml.load" and _keyword(c, "Loader") is None]


def _pickle_load(tree):
    return [(c.lineno, f"{name}()") for c, name in _calls(tree)
            if name in ("pickle.load", "pickle.loads")]


def _weak_hash(tree):
    return [(c.lineno, f"{name}() not marked usedforsecurity=False")
            for c, name in _calls(tree)
            if name in ("hashlib.md5", "hashlib.sha1")
            and not _is(_keyword(c, "usedforsecurity"), False)]


def _verify_off(tree):
    return [(c.lineno, f"{name or 'call'}(verify=False)")
            for c, name in _calls(tree) if _is(_keyword(c, "verify"), False)]


def _mktemp(tree):
    return [(c.lineno, "tempfile.mktemp() races between name and open")
            for c, name in _calls(tree) if name == "tempfile.mktemp"]


def _silent_except(tree):
    return [(h.lineno, "except body is bare pass")
            for h in ast.walk(tree) if isinstance(h, ast.ExceptHandler)
            and len(h.body) == 1 and isinstance(h.body[0], ast.Pass)]


RULES = (
    {"id": "shell-true", "severity": "high", "find": _shell_true,
     "why": "a shell reparses the string, so any interpolated value is argv",
     "probe": "import subprocess\nsubprocess.run(cmd, shell=True)\n",
     "control": "import subprocess\nsubprocess.run(['ls', '-l'])\n"},
    {"id": "eval-exec", "severity": "high", "find": _eval_exec,
     "why": "the argument becomes code with the caller's whole authority",
     "probe": "eval(payload)\n",
     "control": "ast.literal_eval(payload)\n"},
    {"id": "yaml-unsafe-load", "severity": "high", "find": _yaml_unsafe,
     "why": "the default loader constructs arbitrary Python objects",
     "probe": "import yaml\nyaml.load(text)\n",
     "control": "import yaml\nyaml.load(text, Loader=yaml.SafeLoader)\n"},
    {"id": "pickle-load", "severity": "medium", "find": _pickle_load,
     "why": "unpickling runs the reduce method of whatever the bytes name",
     "probe": "import pickle\npickle.loads(blob)\n",
     "control": "import json\njson.loads(blob)\n"},
    {"id": "weak-hash", "severity": "medium", "find": _weak_hash,
     "why": "md5 and sha1 are broken for anything an adversary can choose",
     "probe": "import hashlib\nhashlib.md5(data).hexdigest()\n",
     "control": "import hashlib\nhashlib.md5(data, usedforsecurity=False)\n"},
    {"id": "verify-disabled", "severity": "high", "find": _verify_off,
     "why": "the certificate is fetched and then not checked against anything",
     "probe": "requests.get(url, verify=False)\n",
     "control": "requests.get(url, verify=True)\n"},
    {"id": "mktemp", "severity": "medium", "find": _mktemp,
     "why": "the name is returned before the file exists, so it can be taken",
     "probe": "import tempfile\npath = tempfile.mktemp()\n",
     "control": "import tempfile\nfh = tempfile.NamedTemporaryFile()\n"},
    {"id": "silent-except", "severity": "low", "find": _silent_except,
     "why": "the failure is discarded, so the next reader sees a working run",
     "probe": "try:\n    work()\nexcept Exception:\n    pass\n",
     "control": "try:\n    work()\nexcept Exception as exc:\n    log(exc)\n"},
)

RULES_BY_ID = {rule["id"]: rule for rule in RULES}


def rule_health() -> list:
    """Run every rule against its own probe and control.

    This is the control on a clean scan. `fires` false means the rule found
    nothing in source written to trip it, so any zero it contributed to the
    finding count is a zero about the rule and not about the code. `quiet`
    false means the rule fires on source written to be fine, which spends a
    reader's attention until they stop reading the output at all.
    """
    out = []
    for rule in RULES:
        fires = bool(rule["find"](ast.parse(rule["probe"])))
        quiet = not rule["find"](ast.parse(rule["control"]))
        out.append({"rule_id": rule["id"], "severity": rule["severity"],
                    "fires_on_probe": fires, "quiet_on_control": quiet,
                    "proven": fires and quiet})
    return out
