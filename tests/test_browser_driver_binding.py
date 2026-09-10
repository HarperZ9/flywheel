"""Immutable driver configuration continuity; inert callbacks only."""
import json

import pytest

from harness import browser_control as browser

NOW = '2026-09-09T00:00:00Z'
NAV = {'kind': 'navigate', 'url': 'https://example.test/'}
DIGEST = 'a' * 64


@pytest.fixture(autouse=True)
def clean_registry():
    browser.clear_drivers()
    yield
    browser.clear_drivers()


def register(calls, name='fixture', digest=DIGEST):
    browser.register_driver(name, lambda action: calls.append(action) or {
        'ok': True, 'performed': True}, binding_sha256=digest)


def opened(root, run='r'):
    return browser.open_session(root, run_id=run, at=NOW,
                                policy={'origins': ['https://example.test']})


def act(root, run='r', request='one'):
    return browser.attempt(root, run_id=run, at=NOW, request_id=request, action=NAV)


@pytest.mark.parametrize('digest', [None, '', 'a' * 63, 'G' * 64, 'a' * 65, 1])
def test_invalid_binding_digest_refuses_registration(digest):
    with pytest.raises((TypeError, ValueError)):
        register([], digest=digest)
    assert browser.bound_driver() == (None, None)


def test_missing_digest_is_not_a_legacy_live_driver_bypass():
    with pytest.raises((TypeError, ValueError)):
        browser.register_driver('fixture', lambda action: None)
    assert browser.bound_driver() == (None, None)


def test_binding_survives_policy_admission_driver_and_completion(tmp_path):
    calls = []
    register(calls)
    policy = opened(tmp_path)
    expected = {'name': 'fixture', 'binding_sha256': DIGEST}
    assert policy['policy']['driver_binding'] == expected
    terminal = act(tmp_path)
    records = json.loads(browser.chain_path(tmp_path, 'r').read_text())
    assert terminal['performed'] is True
    assert records[1]['driver_binding'] == expected
    assert records[2]['driver_binding'] == expected
    assert calls[0]['driver_binding'] == expected
    assert calls[0]['request_id'] == 'one'


@pytest.mark.parametrize('name,digest', [('fixture', 'b' * 64), ('replacement', DIGEST)])
def test_changed_binding_refuses_before_call_and_records_reason(tmp_path, name, digest):
    register([])
    opened(tmp_path)
    browser.clear_drivers()
    calls = []
    register(calls, name, digest)
    result = act(tmp_path)
    assert result['admitted'] is False
    assert 'binding' in result['reason']
    assert result['performed'] is False
    assert calls == []


def test_simulation_session_cannot_acquire_live_driver_implicitly(tmp_path):
    opened(tmp_path)
    assert act(tmp_path)['simulated'] is True
    calls = []
    register(calls)
    assert act(tmp_path, request='two')['admitted'] is False
    assert calls == []
    opened(tmp_path, 'explicit-new-session')
    assert act(tmp_path, 'explicit-new-session')['performed'] is True
    assert len(calls) == 1


def test_unregister_only_removes_named_driver_and_does_not_claim_cancellation(tmp_path):
    calls = []
    register(calls)
    register([], 'other')
    browser.unregister_driver('other')
    assert browser.bound_driver()[0] == 'fixture'
    opened(tmp_path)
    browser.unregister_driver('fixture')
    assert act(tmp_path)['admitted'] is False
    assert calls == []
    assert browser.bound_driver() == (None, None)


def test_mutating_callable_metadata_does_not_change_captured_binding(tmp_path):
    class Driver:
        binding_sha256 = DIGEST
        def __call__(self, action):
            return {'ok': True, 'performed': True}
    driver = Driver()
    browser.register_driver('fixture', driver, binding_sha256=driver.binding_sha256)
    opened(tmp_path)
    driver.binding_sha256 = 'b' * 64
    assert act(tmp_path)['driver_binding']['binding_sha256'] == DIGEST


def test_replay_after_registration_change_never_dispatches_again(tmp_path):
    calls = []
    register(calls)
    opened(tmp_path)
    original = act(tmp_path)
    replacements = []
    register(replacements, digest='b' * 64)
    assert act(tmp_path) == original
    assert len(calls) == 1 and replacements == []


def test_caller_policy_cannot_choose_another_driver_binding(tmp_path):
    register([])
    opened_policy = browser.open_session(tmp_path, run_id='r', at=NOW, policy={
        'origins': ['https://example.test'], 'driver_binding': {
            'name': 'replacement', 'binding_sha256': 'b' * 64}})
    assert opened_policy['policy']['driver_binding'] == {
        'name': 'fixture', 'binding_sha256': DIGEST}


@pytest.mark.parametrize('target,mutation', [
    ('policy', 'remove'), ('admission', 'remove'),
    ('admission', 'change'), ('completion', 'change')])
def test_resealed_binding_downgrade_is_not_a_valid_dispatch_history(tmp_path, target, mutation):
    from harness.hash_chain import seal
    calls = []
    register(calls)
    opened(tmp_path)
    act(tmp_path)
    path = browser.chain_path(tmp_path, 'r')
    records = json.loads(path.read_text())
    record = records[{'policy': 0, 'admission': 1, 'completion': 2}[target]]
    container = record['policy'] if target == 'policy' else record
    if mutation == 'remove':
        container.pop('driver_binding')
    else:
        container['driver_binding']['binding_sha256'] = 'b' * 64
    for i, record in enumerate(records):
        if record['kind'] == 'completion':
            record['admission_sha256'] = records[1][browser.DIGEST_KEY]
        record['prev_sha256'] = records[i-1][browser.DIGEST_KEY] if i else ''
        records[i] = seal(record, digest_key=browser.DIGEST_KEY)
    assert browser.chain_intact(records)
    path.write_text(json.dumps(records))
    assert browser.session(tmp_path, run_id='r')['chain_intact'] is False
    with pytest.raises(browser.Refused, match='broken'):
        act(tmp_path, request='new')
    assert len(calls) == 1


def test_capture_is_immutable_but_unregister_does_not_cancel_inflight_action(tmp_path):
    replacements = []
    calls = []
    def first(action):
        calls.append(action)
        browser.unregister_driver('fixture')
        register(replacements, digest='b' * 64)
        assert action['driver_binding']['binding_sha256'] == DIGEST
        return {'ok': True, 'performed': True}
    browser.register_driver('fixture', first, binding_sha256=DIGEST)
    opened(tmp_path)
    assert act(tmp_path)['driver_binding']['binding_sha256'] == DIGEST
    assert act(tmp_path, request='next')['admitted'] is False
    assert len(calls) == 1 and replacements == []


def test_driver_input_mutation_cannot_rewrite_admission_binding(tmp_path):
    def driver(action):
        action['driver_binding']['binding_sha256'] = 'b' * 64
        return {'ok': True, 'performed': True}
    browser.register_driver('fixture', driver, binding_sha256=DIGEST)
    opened(tmp_path)
    assert act(tmp_path)['driver_binding']['binding_sha256'] == DIGEST
    snapshot = browser.session(tmp_path, run_id='r')
    assert snapshot['chain_intact'] is True
    assert snapshot['policy']['driver_binding']['binding_sha256'] == DIGEST
