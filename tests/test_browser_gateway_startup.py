"""Actual gateway bootstrap and registration, without network or credentials."""
import hashlib
import json

import pytest

from harness import browser_control as browser
from harness import gateway
from harness import telos_browser_config as config_module
from harness import telos_browser_registration as registration


@pytest.fixture(autouse=True)
def isolated_gateway(tmp_path, monkeypatch):
    browser.clear_drivers()
    for name in ('root', 'serve_url', 'ollama_url', 'run_root', 'cors',
                 'allowed_hosts', 'flywheel_home', 'auth_token'):
        monkeypatch.setattr(gateway._Handler, name, getattr(gateway._Handler, name, None), raising=False)
    monkeypatch.setenv('FLYWHEEL_HOME', str(tmp_path / 'home'))
    monkeypatch.delenv('FLYWHEEL_TELOS_BROWSER_CONFIG', raising=False)
    calls = []
    def forbid_process(*args, **kwargs):
        raise AssertionError("startup must not invoke an actuator")
    monkeypatch.setattr('harness.telos_browser_adapter.start_owned_process', forbid_process)
    monkeypatch.setattr(gateway, 'load_or_create_token', lambda path: calls.append('token') or 'inert-fixture-token')
    monkeypatch.setattr(gateway, '_bind_hosts', lambda hosts, port: calls.append('bind') or [])
    yield calls
    browser.clear_drivers()


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    node, module = tmp_path / 'node.exe', tmp_path / 'cdp.mjs'
    node.write_bytes(b'inert executable, never run')
    module.write_bytes(b'inert module, never imported')
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    monkeypatch.setattr(config_module, 'SUPPORTED_CDP_SHA256', digest)
    data = {'schema': config_module.SCHEMA, 'node_path': str(node),
            'cdp_module': str(module), 'cdp_sha256': digest, 'port': 9229,
            'browser_instance': '/devtools/browser/fixture', 'target_id': 'fixture',
            'allowed_origin': 'https://example.test'}
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(data))
    return path


def test_gateway_explicit_config_registers_real_adapter_without_actuation(config_path, monkeypatch, isolated_gateway):
    from harness.telos_browser_adapter import TelosBrowserAdapter
    monkeypatch.setenv('FLYWHEEL_TELOS_BROWSER_CONFIG', str(config_path))
    assert gateway.main([]) == 1  # No real server is bound by this fixture.
    name, driver = browser.bound_driver()
    assert name == 'telos-browser' and isinstance(driver, TelosBrowserAdapter)
    assert isolated_gateway == ['token', 'bind']
    policy = browser.open_session(config_path.parent, run_id='r', at='fixture',
                                   policy={'origins': ['https://example.test']})
    assert policy['policy']['driver_binding'] == {
        'name': name, 'binding_sha256': driver.binding_sha256}


@pytest.mark.parametrize('configured', [False, True])
def test_missing_or_invalid_config_removes_stale_registration(tmp_path, monkeypatch, isolated_gateway, configured):
    browser.register_driver('telos-browser', lambda action: None, binding_sha256='a' * 64)
    if configured:
        monkeypatch.setenv('FLYWHEEL_TELOS_BROWSER_CONFIG', str(tmp_path / 'absent.json'))
    assert gateway.main([]) == 1
    assert browser.bound_driver() == (None, None)
    assert isolated_gateway == ['token', 'bind']


def test_unknown_registration_aborts_before_credentials_or_server(monkeypatch, isolated_gateway):
    monkeypatch.setattr(registration, 'configure_telos_browser', lambda path: {
        'available': None, 'code': 'registration_state_unknown', 'driver': None})
    with pytest.raises(SystemExit, match='browser registration state unknown'):
        gateway.main([])
    assert isolated_gateway == []
