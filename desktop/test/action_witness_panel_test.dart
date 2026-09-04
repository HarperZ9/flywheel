// The action-witness panel on screen: paste a run's chain, every link is
// recomputed here, and the panel never calls a linked chain verified when no
// bytes were checked. The records are the shared fixtures from
// tests/test_byte_witness_surface.py. No network, no gateway.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/action_witness_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

const _first = '{"context":{"kind":"input","seq":1},"label":"doc/input",'
    '"length":11,"observed_at":"","prev":"",'
    '"schema":"flywheel.byte-witness/v1",'
    '"sha256":"b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efc'
    'de9","spans":[]}';

const _second = '{"context":{"kind":"output","seq":1},"label":"doc/output",'
    '"length":19,"observed_at":"",'
    '"prev":"dbe349afee22df36ef03ad06e28f8693b46412c48001e22a1c56567897940be'
    '2","schema":"flywheel.byte-witness/v1",'
    '"sha256":"9ecb36561341d18eb65484e833efea61edc74b84cf5e6ae1b81c63533e25f'
    'c8f","spans":[{"end":9,"note":"verb phrase",'
    '"sha256":"22c72aa82ce77c82e2ca65a711c79eaa4b51c57f85f91489ceeacc7b38594'
    '3ba","start":4}]}';

Future<void> _paste(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.tap(find.text('Recheck'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('claims nothing until a chain has been checked', (tester) async {
    await tester.pumpWidget(_wrap(const ActionWitnessPanel()));
    expect(find.textContaining('No chain has been checked yet'), findsOneWidget);
    expect(find.text('REPRODUCED'), findsNothing);
  });

  testWidgets('a linked chain with no bytes reads unverifiable', (tester) async {
    // The ordinary case. The records travel and the bytes do not, so the links
    // hold and nothing reproduced. Calling that verified would be the lie.
    await tester.pumpWidget(_wrap(const ActionWitnessPanel()));
    await _paste(tester, '$_first\n$_second');
    expect(find.text('UNVERIFIABLE'), findsOneWidget);
    expect(find.text('BYTES_UNAVAILABLE'), findsOneWidget);
    expect(find.text('2 records checked'), findsOneWidget);
    expect(find.text('REPRODUCED'), findsNothing);
  });

  testWidgets('shows the head it recomputed', (tester) async {
    await tester.pumpWidget(_wrap(const ActionWitnessPanel()));
    await _paste(tester, '$_first\n$_second');
    expect(find.textContaining('5d592e36e826'), findsOneWidget);
  });

  testWidgets('names the record a broken link broke at', (tester) async {
    await tester.pumpWidget(_wrap(const ActionWitnessPanel()));
    await _paste(tester, _second);          // lifted out of a longer chain
    expect(find.text('TAMPERED'), findsOneWidget);
    expect(find.text('LINK_BROKEN'), findsOneWidget);
    expect(find.text('0 records checked, broke at record 0'), findsOneWidget);
  });

  testWidgets('reads a run result with the chain nested inside it',
      (tester) async {
    await tester.pumpWidget(_wrap(const ActionWitnessPanel()));
    await _paste(tester, '{"action_witness":{"records":[$_first,$_second]}}');
    expect(find.text('UNVERIFIABLE'), findsOneWidget);
    expect(find.text('2 records checked'), findsOneWidget);
  });

  testWidgets('says a parse failure is a parse failure', (tester) async {
    await tester.pumpWidget(_wrap(const ActionWitnessPanel()));
    await _paste(tester, 'not json at all');
    expect(find.textContaining('Nothing in that text reads as witness records'),
        findsOneWidget);
    expect(find.text('TAMPERED'), findsNothing);
  });

  testWidgets('always shows what the chain does not prove', (tester) async {
    await tester.pumpWidget(_wrap(const ActionWitnessPanel()));
    await _paste(tester, '$_first\n$_second');
    expect(find.text('does not prove'), findsOneWidget);
    expect(find.textContaining('nothing is signed here'), findsOneWidget);
  });

  testWidgets('clear puts the panel back to claiming nothing', (tester) async {
    await tester.pumpWidget(_wrap(const ActionWitnessPanel()));
    await _paste(tester, '$_first\n$_second');
    await tester.tap(find.text('Clear'));
    await tester.pumpAndSettle();
    expect(find.textContaining('No chain has been checked yet'), findsOneWidget);
    expect(find.text('UNVERIFIABLE'), findsNothing);
  });
}
