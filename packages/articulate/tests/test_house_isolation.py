"""The house voice never reaches the personal voice.

The house modules and the hook entry points must not import voice_store,
voice_identity or voice_apply at any depth, inside a function included. The
personal profile shapes only text the user says is theirs, through voice apply.
"""
import ast
import pathlib

import pytest

import articulate

PKG = pathlib.Path(articulate.__file__).resolve().parent
ROOT = PKG.parent.parent
PERSONAL = {"voice_store", "voice_identity", "voice_apply"}
HOUSE = ["house", "house_spec", "house_settings", "house_hook", "house_tools", "edit_hook"]


def _direct(name):
    tree = ast.parse((PKG / f"{name}.py").read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            found |= {node.module.split(".")[0]} if node.module else {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("articulate."):
            found.add(node.module.split(".")[1])
        elif isinstance(node, ast.ImportFrom) and node.module == "articulate":
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.Import):
            found |= {a.name.split(".")[1] for a in node.names if a.name.startswith("articulate.")}
    return {f for f in found if (PKG / f"{f}.py").is_file()}


def closure(start):
    seen, todo = set(), [start]
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo.extend(_direct(name) - seen)
    return seen


@pytest.mark.parametrize("mod", HOUSE)
def test_house_paths_never_reach_the_personal_store(mod):
    assert not closure(mod) & PERSONAL, (mod, sorted(closure(mod) & PERSONAL))


def test_the_closure_walker_finds_a_known_edge():
    # Control: the walker is not vacuous. voice_tools reaches voice_store.
    assert "voice_store" in closure("voice_tools")


def test_the_plugin_hook_shims_load_only_their_own_modules():
    for shim, module in (("house_hook.py", "articulate.house_hook"),
                         ("edit_hook.py", "articulate.edit_hook")):
        text = (ROOT / "claude-plugin" / "server" / shim).read_text(encoding="utf-8")
        assert f"from {module} import main" in text
        assert not any(name in text for name in PERSONAL)
