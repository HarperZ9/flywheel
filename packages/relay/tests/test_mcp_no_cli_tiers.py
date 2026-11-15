"""A launch without the agent-CLI tiers never builds, probes or starts a CLI.

The directory plugin launches this way so no saved claude or codex sign-in is
used. Each test spies on every route that starts or locates a program. The
control run with the tiers on shows the spy would see a CLI if one were reached.
"""
import json
from types import SimpleNamespace

import pytest

import relay.local_mcp as m
from relay import cli_tiers, endpoints
from relay._vendor import safe_spawn
from relay.mcp_grants import StartGrants


@pytest.fixture
def spied(monkeypatch, tmp_path):
    calls = []
    done = SimpleNamespace(returncode=0, stdout='9.9.9', stderr='')
    monkeypatch.setattr(safe_spawn, 'resolve', lambda name, *a, **k: calls.append(('resolve', name)) or name)
    monkeypatch.setattr(safe_spawn, 'run', lambda name, *a, **k: calls.append(('run', name)) or done)
    monkeypatch.setattr(cli_tiers.safe_spawn, 'run', lambda name, *a, **k: calls.append(('run', name)) or done)
    monkeypatch.setattr(endpoints, 'cli_allowed', lambda *a, **k: True)
    monkeypatch.setattr(m, '_GRANTS', StartGrants(allow_write=True, allow_exec=True, root=str(tmp_path)))
    return calls


def call(name, **arguments):
    result = m._call({'name': name, 'arguments': arguments})
    return result, json.loads(result['content'][0]['text'])


def cli_rows(body):
    return [t for t in body['tiers'] if t['backend'].endswith(('-plan', '-max'))]


def test_tiers_on_reach_the_cli_control(spied, monkeypatch):
    monkeypatch.setattr(m, '_CLI_TIERS', True)
    _, body = call('local_agent_health', online=True)
    assert cli_rows(body) and spied
    _, doctor = call('relay.doctor')
    assert isinstance(doctor['cli_tiers'], list) and 'remote' in doctor
    assert any(kind == 'run' for kind, _ in spied)


def test_tiers_off_build_probe_and_start_nothing(spied, monkeypatch):
    monkeypatch.setattr(m, '_CLI_TIERS', False)
    _, body = call('local_agent_health', online=True)
    assert not cli_rows(body)
    assert not [b for b in m._backends({'online': True}, True) if isinstance(b, endpoints.CliBackend)]
    for backend in ('claude-plan', 'codex-plan', 'claude-max'):
        result, err = call('local_agent_chat', prompt='synthetic', backend=backend, online=True)
        assert result['isError'] and err['error']['code'] == 'CLI_TIERS_OFF'
        result, err = call('local_agent_run', goal='synthetic', backend=backend, online=True,
                           allow_exec=True)
        assert result['isError'] and err['error']['code'] == 'CLI_TIERS_OFF'
    _, doctor = call('relay.doctor')
    assert doctor['cli_tiers'] == 'off in this launch profile' and 'remote' not in doctor
    _, status = call('relay.status')
    assert status['grants']['agent_cli_tiers'] is False and status['grants']['allow_exec'] is True
    assert spied == []


def test_serve_sets_the_profile_for_the_process():
    import io
    assert m.serve(stdin=io.StringIO(''), stdout=io.StringIO(), grants=StartGrants(), cli_tiers=False) == 0
    assert m._CLI_TIERS is False
    m.serve(stdin=io.StringIO(''), stdout=io.StringIO(), grants=StartGrants())
    assert m._CLI_TIERS is True
