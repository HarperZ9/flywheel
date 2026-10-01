"""False-success controls for the packaged restricted companion checks."""
from copy import deepcopy
import hashlib
import json

import pytest

from harness import tool_mcp
from harness.skill_resources import list_resources
from scripts import check_frozen_tool_mcp as probe
from scripts.frozen_gateway_receipt_smoke import prepare_receipt_smoke_fixture, MISSING_LEAF


def replies(tmp_path):
    home, workspace = tmp_path / 'state', tmp_path / 'workspace'
    home.mkdir()
    workspace.mkdir()
    leaf = prepare_receipt_smoke_fixture(home)
    state = home / 'runs'
    requests = [probe.req(1, 'initialize', {}), probe.req(2, 'tools/list', {}),
                probe.req(3, 'resources/list', {}), probe.call(4, 'flywheel.tool_status', {})]
    requests += [probe.call(rid, 'receipt.verify_inclusion', {'leaf': val})
                 for rid, val in enumerate((leaf, MISSING_LEAF, 'bad'), 5)]
    requests += [probe.req(rid, 'resources/read', {'uri': row['uri']})
                 for rid, row in enumerate(list_resources()['resources'], 8)]
    requests += [probe.call(rid, name, {}) for rid, name in enumerate(probe.DENIED, 10)]
    results = {r['id']: tool_mcp.handle(r, workspace, state)['result'] for r in requests}
    return results, leaf


def replace_payload(row, value):
    row['structuredContent'] = value
    row['content'][0]['text'] = json.dumps(value)


def test_source_fixture_meets_independent_proof_check(tmp_path):
    rows, leaf = replies(tmp_path)
    probe.validate(rows, tool_mcp.installed_version(), leaf)


@pytest.mark.parametrize('mutation', ['version', 'resource', 'tool', 'grant', 'proof', 'refusal', 'missing'])
def test_success_shaped_wrong_result_is_rejected(tmp_path, mutation):
    rows, leaf = replies(tmp_path)
    rows = deepcopy(rows)
    if mutation == 'version':
        rows[1]['serverInfo']['version'] = '0.0.0'
    elif mutation == 'resource':
        rows[8]['contents'][0]['text'] += 'wrong bytes'
    elif mutation == 'tool':
        rows[2]['tools'].append({'name': 'exec'})
    elif mutation == 'grant':
        value = rows[4]['structuredContent']; value['exec'] = True
        replace_payload(rows[4], value)
    elif mutation == 'proof':
        value = rows[5]['structuredContent']; value['proof']['tree_size'] = 9
        replace_payload(rows[5], value)
    elif mutation == 'refusal':
        value = rows[10]['structuredContent']; value['error']['message'] = 'network already attempted'
        replace_payload(rows[10], value)
    elif mutation == 'missing':
        value = rows[6]['structuredContent']; value['included'] = True
        replace_payload(rows[6], value)
    with pytest.raises(RuntimeError):
        probe.validate(rows, tool_mcp.installed_version(), leaf)
