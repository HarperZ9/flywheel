// The finished run's own chain, on the surface where the run finished. The
// result already carries the records, so nothing is pasted and nothing is
// fetched: every link is recomputed here. Vectors are the shared fixtures from
// tests/test_byte_witness_surface.py.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/ide/live_run_tail.dart';
import 'package:flywheel_desktop/models/byte_witness.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/action_witness_line.dart';

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

// A run result as the gateway returns it, with the chain the engine attached.
Map<String, dynamic> _run(List<Map<String, dynamic>> records) => {
      'final': 'done',
      'action_witness': {
        'schema': kByteWitnessSchema,
        'count': records.length,
        'head_sha256': _secondLink,
        'records': records,
      },
    };

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('rechecks the chain the finished run handed over',
      (tester) async {
    // The records travel and the bytes do not. The links hold and nothing
    // reproduced, and that is unverifiable, not verified.
    await tester.pumpWidget(
        _wrap(ActionWitnessLine(run: _run([_first(), _second()]))));
    expect(find.text('UNVERIFIABLE'), findsOneWidget);
    expect(find.text('2 records checked'), findsOneWidget);
    expect(find.textContaining('5d592e36e826'), findsOneWidget);
    expect(find.text('REPRODUCED'), findsNothing);
  });

  testWidgets('reads a rewritten record as tampered', (tester) async {
    final second = _second()..['prev'] = _secondLink;
    await tester
        .pumpWidget(_wrap(ActionWitnessLine(run: _run([_first(), second]))));
    expect(find.text('TAMPERED'), findsOneWidget);
    expect(find.textContaining('broke at record 1'), findsOneWidget);
  });

  testWidgets('says why an over-budget chain is not here', (tester) async {
    await tester.pumpWidget(_wrap(ActionWitnessLine(run: const {
      'action_witness': {
        'schema': kByteWitnessSchema,
        'count': 40,
        'head_sha256': _secondLink,
        'records_omitted': 'over the budget a result carries',
      }
    })));
    expect(find.textContaining('left the records behind'), findsOneWidget);
    expect(find.textContaining('over the budget'), findsOneWidget);
    expect(find.text('TAMPERED'), findsNothing);
    expect(find.text('UNVERIFIABLE'), findsNothing);
  });

  testWidgets('does not go quiet on a run that carried no chain',
      (tester) async {
    // Silence here would read as checked and fine.
    await tester
        .pumpWidget(_wrap(const ActionWitnessLine(run: {'final': 'done'})));
    expect(find.textContaining('handed over no witness chain'), findsOneWidget);
    expect(find.text('UNVERIFIABLE'), findsNothing);
    expect(find.text('REPRODUCED'), findsNothing);
  });

  testWidgets('the live run tail shows it the moment a run finishes',
      (tester) async {
    await tester.pumpWidget(_wrap(LiveRunTail(
      events: [
        {..._run([_first(), _second()]), 'type': 'done'}
      ],
      scroll: ScrollController(),
      client: GatewayClient(),
    )));
    // Kicker uppercases what it is given, so this is the rendered face.
    expect(find.text('ACTION WITNESS'), findsOneWidget);
    expect(find.text('2 records checked'), findsOneWidget);
  });
}
