"""Require actual persisted evidence and refusal effects across process restarts."""
import hashlib
from pathlib import Path

from check_client_common import binding_args, call, environment, event_args, value


def check_workflow(executable, root):
    root = Path(root) / 'workflow'
    root.mkdir()
    state = root / 'context.sqlite'
    env = environment(root)
    args = binding_args(state)
    stored = value(call(executable, root, env, [*args, '--context-write=true'],
                        'canon.context.ingest', event_args()))
    if not state.is_file() or stored.get('status') != 'stored':
        raise ValueError('context ingestion did not persist a database')
    before = hashlib.sha256(state.read_bytes()).hexdigest()
    health = value(call(executable, root, env, args, 'canon.context.health'))
    queried = value(call(executable, root, env, args, 'canon.context.query', {'query': 'telescope'}))
    got = value(call(executable, root, env, args, 'canon.context.get', {'record_id': stored['event_record_id']}))
    if not queried.get('hits') or 'telescope' not in str(queried['hits']):
        raise ValueError('query did not recover persisted synthetic evidence')
    record = got.get('record', {})
    if (record.get('data', {}).get('message_text') != 'Synthetic telescope context.'
            or record.get('provenance', {}).get('source_hash') != stored.get('source_hash')):
        raise ValueError('get did not preserve original content and provenance')
    if not health.get('ok') or health.get('context_write') is not False:
        raise ValueError('read-only restart did not retain the explicit profile')
    if not (health.get('store_id') == queried.get('store_id') == got.get('store_id') == stored.get('store_id')):
        raise ValueError('persistent store identity changed across restarts')
    check_refusals(executable, root, env, args, stored['event_record_id'])
    if hashlib.sha256(state.read_bytes()).hexdigest() != before:
        raise ValueError('read-only workflow modified database bytes')
    if set(p.name for p in root.iterdir()) != {'context.sqlite'}:
        raise ValueError('read-only workflow left unexpected sidecar state')
    return {'status': 'PASS', 'scope': 'ingest, restarted read-only query/get, provenance, scope/write/purge refusal',
        'does_not_prove': ['semantic retrieval quality', 'OS sandbox confinement', 'installed client compatibility']}


def check_refusals(executable, root, env, args, record_id):
    refused = [('canon.context.ingest', event_args()), ('unknown_destructive_tool', {}),
        ('canon.context.purge', {'all': True}),
        ('canon.context.query', {'query': 'telescope', 'project_id': 'foreign'}),
        ('canon.context.get', {'record_id': record_id, 'context_db': str(root / 'foreign.sqlite')}),
        ('canon.context.ingest', {**event_args(), 'context_write': True})]
    for name, arguments in refused:
        result = call(executable, root, env, args, name, arguments)
        if not result.get('isError'):
            raise ValueError('ungranted or cross-scope operation accepted: ' + name)
