// A stored run gets the same byte-witness recheck a live one gets. Reopening
// a run months later reads it exactly as strictly as watching it finish, and
// a stored run that carried no chain says so rather than going quiet.
// Vectors are the shared fixtures from tests/test_byte_witness_surface.py.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/ide/agent_runs_panel.dart';
import 'package:flywheel_desktop/models/byte_witness.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';

const _firstLink =
    'dbe349afee22df36ef03ad06e28f8693b46412c48001e22a1c56567897940be2';
const _secondLink =
    '5d592e36e826fe6f35d25d3627d5ef28f05556dd3408e75866daa6297aa3ce9c';

Map<String, dynamic> _first() => {
      'context': {'kind': 'input', 'seq': 1},
      'label': 'doc/input',
      'length': 11,
      'observed_at': '',
      'prev': '',
      'schema': kByteWitnessSchema,
      'sha256':
          'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9',
      'spans': <dynamic>[],
    };

Map<String, dynamic> _second() => {
      'context': {'kind': 'output', 'seq': 1},
      'label': 'doc/output',
      'length': 19,
      'observed_at': '',
      'prev': _firstLink,
      'schema': kByteWitnessSchema,
      'sha256':
          '9ecb36561341d18eb65484e833efea61edc74b84cf5e6ae1b81c63533e25fc8f',
      'spans': <dynamic>[
        {
          'end': 9,
          'note': 'verb phrase',
          'sha256':
              '22c72aa82ce77c82e2ca65a711c79eaa4b51c57f85f91489ceeacc7b385943ba',
          'start': 4,
        },
      ],
    };

// A stored run as agent_run_detail returns it: the whole result document the
// engine saved, with the chain still inside it.
Map<String, dynamic> _stored({bool intact = true, bool witnessed = true}) => {
      'run_id': 'a1b2c3d4e5f60718',
      'intact': intact,
      'final': 'done',
      'goal_excerpt': 'read one file',
      'started': '2026-09-04T12:00:00',
      if (witnessed)
        'action_witness': {
          'schema': kByteWitnessSchema,
          'count': 2,
          'head_sha256': _secondLink,
          'records': [_first(), _second()],
        },
    };

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('a stored run is rechecked, not just displayed', (tester) async {
    await tester.pumpWidget(_wrap(StoredAgentRun(doc: _stored())));
    expect(find.text('ACTION WITNESS'), findsOneWidget);
    expect(find.text('2 records checked'), findsOneWidget);
    // The records travel and the bytes do not, here as anywhere else.
    expect(find.text('UNVERIFIABLE'), findsOneWidget);
    expect(find.text('REPRODUCED'), findsNothing);
  });

  testWidgets('names the record a rewrite broke the chain at', (tester) async {
    // Rewriting the LAST record only moves the head. Rewriting an earlier one
    // is what leaves the record after it pointing at a link that no longer
    // exists, which is the thing a chain is for.
    final doc = _stored();
    ((doc['action_witness'] as Map)['records'] as List)[0] = _first()
      ..['label'] = 'doc/rewritten';
    await tester.pumpWidget(_wrap(StoredAgentRun(doc: doc)));
    expect(find.text('TAMPERED'), findsOneWidget);
    expect(find.text('1 records checked, broke at record 1'), findsOneWidget);
  });

  testWidgets('a stored run with no chain does not go quiet', (tester) async {
    await tester.pumpWidget(_wrap(StoredAgentRun(doc: _stored(witnessed: false))));
    expect(find.textContaining('handed over no witness chain'), findsOneWidget);
  });

  testWidgets('the tampered banner still covers everything below it',
      (tester) async {
    // The content-address covers the whole document, so a run that fails it
    // could have had its chain rewritten with it. The banner is what says the
    // chain below cannot be read as reassurance, and it must still be there.
    await tester.pumpWidget(_wrap(StoredAgentRun(doc: _stored(intact: false))));
    expect(find.textContaining('cannot be trusted as the original trace'),
        findsOneWidget);
    expect(find.text('ACTION WITNESS'), findsOneWidget);
  });
}
