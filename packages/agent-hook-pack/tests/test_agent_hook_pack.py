from pathlib import Path

from agent_hook_pack import hook_pack


def write_hook(root: Path, name: str, body: str = "echo ok\n") -> Path:
    path = root / name
    shebang = "#!/usr/bin/env python\n" if name.endswith(".py") else "#!/usr/bin/env bash\n"
    path.write_text(shebang + body, encoding="utf-8")
    return path


def write_required_hooks(root: Path) -> None:
    for name in hook_pack.EXPECTED_HOOKS:
        write_hook(root, name)


def test_audit_finds_expected_hooks() -> None:
    hooks = hook_pack.discover_hooks(hook_pack.HOOK_DIR)
    assert len(hooks) >= 5
    assert any(path.name == "block-secrets.py" for path in hooks)


def test_packaged_hooks_pass_audit() -> None:
    assert hook_pack.audit_hooks(hook_pack.HOOK_DIR) == []


def test_audit_reports_missing_required_hook(tmp_path: Path) -> None:
    for name in hook_pack.EXPECTED_HOOKS - {"verify-no-secrets.sh"}:
        write_hook(tmp_path, name)

    findings = hook_pack.audit_hooks(tmp_path)

    assert (str(tmp_path / "verify-no-secrets.sh"), "required_hook_missing") in findings


def test_audit_reports_empty_hook(tmp_path: Path) -> None:
    write_required_hooks(tmp_path)
    (tmp_path / "block-secrets.py").write_text("", encoding="utf-8")

    findings = hook_pack.audit_hooks(tmp_path)

    assert (str(tmp_path / "block-secrets.py"), "hook_empty") in findings


def test_audit_reports_unexpected_shebang(tmp_path: Path) -> None:
    write_required_hooks(tmp_path)
    (tmp_path / "check-branch.sh").write_text(
        "#!/usr/bin/env python\nprint('wrong runtime')\n",
        encoding="utf-8",
    )

    findings = hook_pack.audit_hooks(tmp_path)

    assert (str(tmp_path / "check-branch.sh"), "shebang_unexpected") in findings


def test_audit_detects_synthetic_secret_pattern(tmp_path: Path) -> None:
    write_required_hooks(tmp_path)
    synthetic = "ghp_" + ("A" * 24)
    (tmp_path / "block-secrets.py").write_text(
        "#!/usr/bin/env python\nTOKEN = '" + synthetic + "'\n",
        encoding="utf-8",
    )

    findings = hook_pack.audit_hooks(tmp_path)

    assert (str(tmp_path / "block-secrets.py"), "secret_pattern_0") in findings


def test_install_hooks(tmp_path: Path) -> None:
    target = tmp_path / "hooks"
    count = hook_pack.install_hooks(hook_pack.HOOK_DIR, target)
    assert count >= 5
    assert (target / "block-secrets.py").exists()
    assert (target / "check-branch.sh").exists()
    assert (target / "lint-on-save.sh").exists()
