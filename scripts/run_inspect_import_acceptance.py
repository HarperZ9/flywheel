"""Run real Inspect serialization with a mock model, then import its JSON locally.

Requires inspect-ai==0.3.263 in a separate development environment. No model
credentials or external model calls. Output contains local evaluation metadata.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--epochs', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.log import read_eval_log, write_eval_log
    from inspect_ai.model import ModelOutput, get_model
    from inspect_ai.scorer import match
    from inspect_ai.solver import generate
    from harness.inspect_evidence import import_inspect_log
    from harness.inspect_fixture_contract import INSPECT_VERSION

    if version('inspect-ai') != INSPECT_VERSION:
        parser.error('Inspect producer version differs from the reviewed fixture contract')

    root = args.out.absolute()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        parser.error('--out must be an empty directory; existing evidence is preserved')
    task = Task(name='flywheel_inspect_import', dataset=[
        Sample(id='correct', input='Return four.', target='four'),
        Sample(id='incorrect', input='Return four.', target='four'),
    ], solver=generate(), scorer=match(), epochs=args.epochs)
    expected_scores = ['C', 'I'] * args.epochs
    model = get_model('mockllm/model', custom_outputs=[
        ModelOutput.from_content(model='mockllm', content=value)
        for value in ['four', 'five'] * args.epochs
    ])
    logs = eval(task, model=model, log_dir=str(root), log_format='eval',
                display='none', max_samples=1, log_model_api=False)
    log = read_eval_log(logs[0].location)
    exported = root / 'inspect.json'
    write_eval_log(log, str(exported), format='json')
    raw = exported.read_bytes()
    report = import_inspect_log(raw)
    assert log.status == 'success'
    assert [s.scores['match'].value for s in log.samples or []] == expected_scores
    assert report['reported_status'] == 'success'
    assert report['assessment'] == 'reported'
    assert report['counts']['total_samples'] == 2 * args.epochs
    assert report['counts']['completed_samples'] == 2 * args.epochs
    # max_samples=1 above limits parallel work, not dataset coverage.
    assert report['counts']['config_limit'] is None
    assert report['semantic_verification'] == 'UNVERIFIABLE'
    assert report['source']['sha256'] == hashlib.sha256(raw).hexdigest()
    assert [sample['scores'][0]['value'] for sample in report['samples']] == expected_scores
    source = json.loads(raw)
    for reference in report['source_pointers']:
        value = source
        for part in reference['json_pointer'].split('/')[1:]:
            key = part.replace('~1', '/').replace('~0', '~')
            value = value[int(key)] if isinstance(value, list) else value[key]
        assert value == reference['source_value']
    invalidated_path = root / 'inspect-invalidated.json'
    write_eval_log(log.model_copy(update={'invalidated': True}),
                   str(invalidated_path), format='json')
    invalidated_report = import_inspect_log(invalidated_path.read_bytes())
    assert invalidated_report['invalidated'] is True
    assert invalidated_report['assessment'] == 'incomplete'
    assert invalidated_report['scoring_coverage']['coverage_complete'] is False
    assert {'json_pointer': '/invalidated', 'source_value': True} in invalidated_report['source_pointers']
    (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    receipt = {'inspect_version': version('inspect-ai'),
               'source_sha256': hashlib.sha256(raw).hexdigest(),
               'reported_status': log.status, 'reported_scores': expected_scores,
               'epochs': args.epochs,
               'invalidated_control_assessment': invalidated_report['assessment'],
               'semantic_verification': report['semantic_verification'],
               'does_not_prove': 'Model capability, independent scoring or governance compliance.'}
    (root / 'acceptance.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
