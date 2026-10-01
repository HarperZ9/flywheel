"""Disposable hosted-Windows installed UI acceptance; never an operator-host probe."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from desktop.tool import installed_native_close
from desktop.tool.installed_payload_binding import _scan_files
from desktop.tool.native_close_acceptance import _run_powershell
from scripts.check_installed_tool_profiles import bound_identity, digest, require
from scripts.check_installed_canon_context import _resolve_engine, _reject_reparse_chain


def hosted_windows():
    require(os.name == 'nt' and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('RUNNER_OS') == 'Windows', 'DISPOSABLE_HOSTED_WINDOWS_REQUIRED')
    root = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(root.is_dir(), 'RUNNER_TEMP_REQUIRED')
    return root


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@contextmanager
def block_external_network(install_root):
    # CI-only rules cover every installed executable, including bundled lane runtimes.
    group = 'Flywheel-Acceptance-' + uuid.uuid4().hex
    executables = [path for _, path in _scan_files(install_root) if path.suffix.lower() == '.exe']
    require(bool(executables), 'INSTALLED_EXECUTABLES_MISSING')
    remote = "'0.0.0.0-126.255.255.255','128.0.0.0-255.255.255.255','::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'"
    try:
        _run_powershell("$ErrorActionPreference='Stop'; $profiles = @(Get-NetFirewallProfile); "
            "if ($profiles.Count -ne 3 -or @($profiles | Where-Object { -not $_.Enabled }).Count) "
            "{ throw 'firewall profiles must be enabled' }")
        for number, path in enumerate(executables):
            _run_powershell("$ErrorActionPreference='Stop'; New-NetFirewallRule -DisplayName "
                + ps_quote(group + '-' + str(number)) + ' -Group ' + ps_quote(group)
                + ' -Direction Outbound -Action Block -Profile Any -Enabled True -Program '
                + ps_quote(path) + ' -RemoteAddress ' + remote + ' | Out-Null')
        yield
    finally:
        _run_powershell("$ErrorActionPreference='Stop'; Get-NetFirewallRule -Group "
            + ps_quote(group) + ' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction Stop')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-root', required=True, type=Path)
    parser.add_argument('--expected-app-sha256', required=True)
    parser.add_argument('--expected-engine-sha256', required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args(argv)
    receipt = {'schema': 'flywheel.installed-native-ui/v1', 'verdict': 'HOLD', 'stage': 'host',
        'limits': ['Disposable hosted Windows session only; no operator device acceptance.',
                   'Window creation, bundled engine ownership and native close only.',
                   'No rendered-content, interaction, accessibility, voice or model-quality acceptance.',
                   'Registry installation and complete payload binding belong to the outer CI gate.']}
    work = None
    try:
        runner_temp = hosted_windows()
        work = runner_temp / ('flywheel-native-ui-' + uuid.uuid4().hex)
        work.mkdir()
        receipt['stage'] = 'identity'
        engine = _resolve_engine(args.install_root)
        root = engine.parent.parent
        app = root / 'flywheel_desktop.exe'
        _reject_reparse_chain(app, 'APP_REPARSE_POINT')
        require(digest(app) == args.expected_app_sha256, 'APP_SHA256_MISMATCH')
        bound_identity(engine, args.expected_version, args.source_commit, args.expected_engine_sha256)
        receipt['stage'] = 'network_isolation'
        with block_external_network(root):
            result = installed_native_close.run(root, work / 'profile')
        receipt.update(result)
        receipt['stage'] = 'final_identity' if result['verdict'] == 'PASS' else result['stage']
        bound_identity(engine, args.expected_version, args.source_commit, args.expected_engine_sha256)
        require(digest(app) == args.expected_app_sha256, 'APP_SHA256_CHANGED')
        if result['verdict'] == 'PASS':
            receipt.update(stage='complete', app_sha256=args.expected_app_sha256,
                engine_sha256=args.expected_engine_sha256, source_commit=args.source_commit,
                version=args.expected_version, external_network_blocked=True)
    except Exception:
        receipt.update(verdict='HOLD', failure='INSTALLED_NATIVE_UI_ACCEPTANCE_FAILED')
        if work is not None:
            (work / 'failure.local.txt').write_text(traceback.format_exc(), encoding='utf-8')
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'schema': receipt['schema'], 'verdict': receipt['verdict'], 'stage': receipt['stage']}))
    return 0 if receipt['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
