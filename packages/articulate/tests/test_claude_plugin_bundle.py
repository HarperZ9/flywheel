"""The Claude plugin build: what it writes, and the rules it is held to.

scripts/build_claude_plugin.py copies claude-plugin/, the package source and
LICENSE into a folder that becomes the root of the plugin's own repository.
These tests build it, check it against scripts/claude_plugin_rules.py, and
confirm the bundled source is the package byte for byte. Each rule has a planted
break below, so a clean build is a finding and not a rule that never fires.
The documents a plugin user reads are held to the house profile and the origin
wording rules that the rest of the docs follow.
"""
import json
import pathlib
import subprocess
import sys

import pytest

import articulate
from articulate import local_mcp, mcp_server, profiles
from claude_plugin_helpers import (PLUGIN_ENV, ROOT, SERVER, SKILL, TEMPLATE,
                                   callable_name, load)
import re

SURFACE_CLAIM = re.compile(
    r"(?i)\bai[- ](?:tells?|register|prose|generated|authored|written)\b|\bai prose\b"
    r"|\b(?:HIGH|MEDIUM|LOW|prose|writing) tells?\b|\btells appear\b|\bchat tool\b"
    r"|\bchat reply\b|\bdetects? ai\b|\bhuman[- ]written\b|\bmachine[- ]written\b")

build = load("build_claude_plugin")
rules = load("claude_plugin_rules")
PKG = pathlib.Path(articulate.__file__).parent


@pytest.fixture(scope="module")
def plugin(tmp_path_factory):
    out = tmp_path_factory.mktemp("built") / "articulate-writing"
    build.build(out)
    return out


def test_the_build_passes_every_rule(plugin):
    assert rules.check_bundle(plugin) == []


def _tracked_files(folder):
    """The files git tracks under folder that exist, relative to it, or None. The
    build ships exactly these, minus caches and bytecode."""
    git = load("find_program").find_program("git", avoid=[ROOT])
    if git is None:
        return None
    try:
        run = subprocess.run([git, "ls-files", "-z", "--cached", folder], cwd=ROOT,
                             capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if run.returncode != 0:
        return None
    names = [n.decode("utf-8") for n in run.stdout.split(b"\0") if n]
    return sorted(n[len(folder) + 1:] for n in names
                  if (ROOT / n).is_file() and "__pycache__" not in n)


def test_the_bundled_source_is_the_server_closure_byte_for_byte(plugin):
    """The bundle holds the modules the server can import and the package's other
    files, each byte for byte, and none of the modules it never imports."""
    bundled = plugin / "src" / "articulate"
    shipped = sorted(p.relative_to(bundled).as_posix()
                     for p in bundled.rglob("*") if p.is_file())
    tracked = _tracked_files("src/articulate")
    assert tracked is not None, "the build reads the files git tracks, so this test does"
    assert set(shipped) <= set(tracked)
    assert {f for f in tracked if not f.endswith(".py")} <= set(shipped)
    assert "local_mcp.py" in shipped and "__init__.py" in shipped and "py.typed" in shipped
    for never_imported in ("cli.py", "lsp_server.py", "fairness.py", "bench.py"):
        assert never_imported not in shipped, never_imported
    for rel in shipped:
        assert (bundled / rel).read_bytes() == (PKG / rel).read_bytes(), rel


def _package_imports(path):
    """The articulate module names one source file imports, at any depth."""
    import ast
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            names |= {node.module.split(".")[0]} if node.module else {
                a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "articulate."):
            names.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            names |= {a.name.split(".")[1] for a in node.names
                      if a.name.startswith("articulate.")}
    return names


def test_every_package_import_in_the_bundle_resolves_inside_it(plugin):
    bundled = plugin / "src" / "articulate"
    modules = {p.stem for p in bundled.glob("*.py")}
    package = {p.stem for p in PKG.glob("*.py")}
    for path in sorted(bundled.glob("*.py")):
        # Hosted-only modules stay out on purpose; the import that names them
        # sits behind a guard that answers without them.
        missing = (_package_imports(path) & package) - modules - build.HOSTED_ONLY
        assert not missing, (path.name, sorted(missing))


def test_every_bundled_module_imports_with_only_the_bundle_and_the_stdlib(plugin):
    names = sorted(p.stem for p in (plugin / "src" / "articulate").glob("*.py")
                   if p.stem != "__init__")
    code = ("import importlib, sys; sys.path.insert(0, %r)\n"
            "for n in %r: importlib.import_module('articulate.' + n)\n"
            "print(sorted(m for m in sys.modules if m.startswith('articulate')) == "
            "sorted(['articulate'] + ['articulate.' + n for n in %r]))\n"
            % (str(plugin / "src"), names, names))
    run = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    assert run.stdout.strip() == "True"


def test_every_tracked_template_file_lands_unchanged_and_nothing_else(plugin):
    expected = _tracked_files("claude-plugin")
    assert expected is not None, "the build reads the files git tracks, so this test does"
    # claude-plugin/src is the vendored package copy; the build writes src/ from
    # src/articulate, and test_claude_plugin_vendored holds the two equal.
    expected = [rel for rel in expected if not rel.startswith("src/")]
    landed = sorted(p.relative_to(plugin).as_posix() for p in plugin.rglob("*")
                    if p.is_file() and p.relative_to(plugin).parts[0] != "src"
                    and p.relative_to(plugin).as_posix() != "LICENSE")
    assert landed == expected
    for rel in expected:
        assert (plugin / rel).read_bytes() == (TEMPLATE / rel).read_bytes(), rel
    assert (plugin / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()


def test_the_build_refuses_a_folder_holding_other_files(tmp_path):
    (tmp_path / "notes.txt").write_text("keep me\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        build.build(tmp_path, replace=True)
    assert (tmp_path / "notes.txt").is_file()


def test_the_build_refuses_to_overwrite_without_replace(tmp_path):
    build.build(tmp_path / "out")
    with pytest.raises(SystemExit):
        build.build(tmp_path / "out")


def test_replace_rebuilds_in_place_and_keeps_git(tmp_path):
    out = tmp_path / "out"
    build.build(out)
    (out / ".git").mkdir()
    (out / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (out / "server" / "stale.py").write_text("x = 1\n", encoding="utf-8")
    build.build(out, replace=True)
    assert (out / ".git" / "HEAD").is_file()
    assert not (out / "server" / "stale.py").exists()
    assert rules.check_bundle(out) == []


def _edit(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def _edit_json(path, change):
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def _server(data):
    return data["mcpServers"]["articulate"]


BREAKS = {
    "large-file": (lambda p: (p / "server" / "big.txt").write_text("x" * 262144),
                   "256 KiB"),
    "binary-file": (lambda p: (p / "server" / "blob.txt").write_bytes(b"\x00\xff"),
                    "not a text file"),
    "bin-folder": (lambda p: (p / "bin").mkdir(), "bin must not"),
    "claude-md": (lambda p: (p / "CLAUDE.md").write_text("x\n"), "CLAUDE.md must not"),
    "gitattributes": (lambda p: (p / ".gitattributes").write_text("* text=auto\n"),
                      ".gitattributes must not"),
    "bytecode": (lambda p: ((p / "src" / "articulate" / "__pycache__").mkdir(),
                            (p / "src" / "articulate" / "__pycache__" / "x.txt")
                            .write_text("x")), "cache file"),
    "em-dash": (lambda p: _edit(p / "README.md", "before you ship it.",
                                "before you ship it \u2014 fast."), "em dash"),
    "open-source": (lambda p: _edit(p / "SECURITY.md", "# Security",
                                    "# Security\n\nAn open-source plugin."), "open source"),
    "local-path": (lambda p: _edit(p / "README.md", "## Limits",
                                   "Saved in C:\\Users\\me\\notes.\n\n## Limits"),
                   "local file path"),
    "policy-topic": (lambda p: _edit(p / "README.md", "**Retention.**", "**Keeping.**"),
                     "does not cover Retention"),
    "policy-drift": (lambda p: _edit(p / "PRIVACY.md", "Last updated", "Updated"),
                     "PRIVACY.md differs"),
    "version": (lambda p: _edit_json(p / ".claude-plugin" / "plugin.json",
                                     lambda d: d.update(version="9.9.9")),
                "version differs"),
    "marketplace-version": (lambda p: _edit_json(
        p / ".claude-plugin" / "marketplace.json",
        lambda d: d["plugins"][0].update(version="0.5.0")), "plugin.json only"),
    "interpreter": (lambda p: _edit_json(p / ".mcp.json",
                                         lambda d: _server(d).update(command="python")),
                    "command must be python3"),
    "second-variable": (lambda p: _edit_json(p / ".mcp.json", lambda d: _server(d)[
        "args"].append("${CLAUDE_PLUGIN_DATA}/log")), "the only variable"),
    "skill-name": (lambda p: _edit(p / "skills" / "prose-review" / "SKILL.md",
                                   "name: prose-review", "name: review-prose"),
                   "equal the folder"),
    "skill-tool": (lambda p: _edit(p / "skills" / "prose-review" / "SKILL.md",
                                   "name: prose-review", "name: prose-review\nallowed-tools: Bash"),
                   "allowed tool Bash"),
    "secret-name": (lambda p: (p / ".env").write_text("TOKEN=1\n"), "credential"),
    "secret-text": (lambda p: (p / "server" / "notes.txt").write_text(
        "key sk-" + "ant-" + "PLANTED-for-a-test-0000\n"), "credential"),
    "hook-blocking": (lambda p: _edit_json(p / "hooks" / "hooks.json", lambda d: d[
        "hooks"].update(PreToolUse=d["hooks"].pop("PostToolUse"))), "differs from the declared"),
    "hook-command": (lambda p: _edit_json(p / "hooks" / "hooks.json", lambda d: d[
        "hooks"]["PostToolUse"][0]["hooks"][0].update(command="sh -c 'curl x'")),
        "differs from the declared"),
    "house-hook-command": (lambda p: _edit_json(p / "hooks" / "hooks.json", lambda d: d[
        "hooks"]["SessionStart"][0]["hooks"][0].update(command="sh -c 'curl x'")),
        "differs from the declared"),
    "stop-hook-dropped": (lambda p: _edit_json(p / "hooks" / "hooks.json", lambda d: d[
        "hooks"].pop("Stop")), "differs from the declared"),
    "house-hook-script": (lambda p: (p / "server" / "house_hook.py").unlink(),
                          "house_hook.py is missing"),
    "hook-script": (lambda p: (p / "server" / "edit_hook.py").unlink(),
                    "edit_hook.py is missing"),
    "codex-hooks": (lambda p: _edit_json(p / ".codex-plugin" / "plugin.json",
                                         lambda d: d.pop("hooks")), "identity or OpenAI"),
    "listing-url": (lambda p: _edit_json(p / ".claude-plugin" / "plugin.json",
                                         lambda d: d.update(supportUrl="http://example.com")),
                    "supportUrl must be an https URL"),
    "icon-missing": (lambda p: (p / ".claude-plugin" / "icon.png").unlink(), "icon"),
    "icon-not-square": (lambda p: (p / ".claude-plugin" / "icon.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + bytes(4) + b"IHDR" + (1024).to_bytes(4, "big")
        + (512).to_bytes(4, "big")), "square PNG"),
    "image-truncated": (lambda p: (p / "server" / "art.png").write_bytes(b"not an image"),
                        "not a complete .png image"),
    "listing-in-portable": (lambda p: _edit_json(p / "plugin.json",
                                                 lambda d: d.update(icon="./x.png")),
                            "portable identity"),
    "short-readme": (lambda p: (p / "README.md").write_text(
        "# Articulate\n\n## Privacy Policy\n\nNone.\n", encoding="utf-8"),
        "fewer than 40 words"),
}


@pytest.mark.parametrize("name", sorted(BREAKS))
def test_each_rule_catches_its_planted_break(tmp_path, name):
    out = tmp_path / "out"
    build.build(out)
    mutate, expected = BREAKS[name]
    mutate(out)
    problems = rules.check_bundle(out)
    assert any(expected in p for p in problems), problems


PLUGIN_DOCS = sorted(TEMPLATE.rglob("*.md")) + [ROOT / "docs" / "claude-plugin.md"]


@pytest.mark.parametrize("path", PLUGIN_DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_plugin_docs_pass_the_release_default_profile(path):
    result = articulate.check_text(path.read_text(encoding="utf-8"),
                                   profile=profiles.load(profiles.DEFAULT))
    hits = [f"L{f['line']} {f['match']!r}" for f in result["high"] + result["medium"]]
    assert result["gate"] == "ok", hits


@pytest.mark.parametrize("path", PLUGIN_DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_plugin_docs_name_no_origin(path):
    text = path.read_text(encoding="utf-8")
    assert not SURFACE_CLAIM.search(text), SURFACE_CLAIM.search(text).group(0)


def test_the_skill_uses_available_local_tools_without_a_host_specific_allowlist():
    text = SKILL.read_text(encoding="utf-8")
    assert "allowed-tools" not in rules.skill_front_matter(text)
    assert "mcp__plugin_" not in text
    listed = {t["name"]: t for t in local_mcp.listed_tools(PLUGIN_ENV)}
    for name in ("check", "score"):
        assert f"`{name}`" in text
        assert listed[name]["annotations"]["readOnlyHint"]


def test_every_callable_tool_name_fits_in_64_characters():
    for tool in local_mcp.listed_tools(PLUGIN_ENV):
        assert len(callable_name(tool["name"])) <= 64, callable_name(tool["name"])


def test_the_result_fields_the_skill_names_exist():
    text = SKILL.read_text(encoding="utf-8")
    long = "By leveraging cutting-edge technology, teams move faster.\n\n" * 80
    result = mcp_server.do_check(long, 50)
    for field in ("clean", "verdict", "hits_omitted"):
        assert f"`{field}`" in text and field in result, field
    assert "`label`" in text and "label" in result["hits"][0]
    check = next(t for t in local_mcp.TOOLS if t["name"] == "check")
    assert "`max_hits`" in text and "max_hits" in check["inputSchema"]["properties"]


def _section(text, heading):
    return text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def test_the_readme_describes_the_launch_the_plugin_declares():
    readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
    runs = _section(readme, "What it runs")
    assert " ".join([SERVER["command"]] + SERVER["args"][:-1]) in runs
    for name, value in PLUGIN_ENV.items():
        assert f"{name}={value}" in runs


def test_the_readme_offers_at_least_three_example_prompts():
    readme = (TEMPLATE / "README.md").read_text(encoding="utf-8")
    prompts = [ln for ln in _section(readme, "Try it").splitlines() if ln.startswith("- \"")]
    assert len(prompts) >= 3, prompts
