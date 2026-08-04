// The signed eval receipt does on screen what the engine promises: a run seals
// a receipt with per-task verdicts, an aggregate, and the seal hex; VERIFY shows
// MATCH; and CORRUPT ONE BYTE flips a single hex char of a COPY of the receipt
// and re-verifies THAT — the same verifier refuses and NAMES the failing check,
// while the stored receipt is never touched. Faked callbacks, no network.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/eval_receipt_panel.dart';

final _goodHex = List.filled(64, 'a').join(); // a well-formed 64-hex seal

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Map<String, dynamic> _runDoc() => {
      'results': [
        {'task_id': 'add_two', 'verdict': 'PASS', 'accepted': 'true'},
        {'task_id': 'max_of_three', 'verdict': 'PASS', 'accepted': 'true'},
        {'task_id': 'is_palindrome', 'verdict': 'UNVERIFIABLE', 'accepted': 'false'},
      ],
      'model_ref': 'stub:model',
      'receipt_file': 'eval-receipt-stub-abc-aaaaaaaaaaaa.json',
      'receipt': {
        'schema': 'flywheel.eval-receipt/v1',
        'seal': {'algorithm': 'sha256', 'hex': _goodHex},
      },
    };

// A faithful fake verifier: the good seal is MATCH, anything else is refused
// with a named failure class — exactly what the offline verifier does.
Map<String, dynamic> _verify(Map<String, dynamic> receipt) {
  final hex = '${(receipt['seal'] as Map)['hex']}';
  if (hex == _goodHex) {
    return {'verdict': 'MATCH', 'failure_class': '', 'detail': '3 results verified'};
  }
  return {
    'verdict': 'TAMPERED',
    'failure_class': 'SEAL_MISMATCH',
    'detail': 'seal sha256:aaaaaaaaaaaa, recomputed sha256:0badbadbad00',
  };
}

EvalReceiptPanel _panel({
  List<EndpointRow>? endpoints,
  String? endpoint = 'stub',
  Future<Map<String, dynamic>> Function()? onRun,
  Future<Map<String, dynamic>> Function(Map<String, dynamic>)? onVerify,
}) =>
    EvalReceiptPanel(
      endpoints: endpoints ??
          [
            EndpointRow(
                name: 'stub',
                backend: 'stub',
                credential: 'present',
                providerRole: '',
                configured: true),
          ],
      endpoint: endpoint,
      model: null,
      onEndpoint: (_) {},
      onModel: (_) {},
      loadModels: () async => {'models': []},
      onRun: onRun ?? (() async => _runDoc()),
      onVerify: onVerify ?? ((r) async => _verify(r)),
    );

void main() {
  testWidgets('no receipt yet is stated, not blank', (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    expect(find.textContaining('No receipt yet'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Run eval'), findsOneWidget);
  });

  testWidgets('a run seals a receipt: tasks, aggregate, and seal hex show',
      (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    await tester.tap(find.widgetWithText(FilledButton, 'Run eval'));
    await tester.pumpAndSettle();
    expect(find.text('add_two'), findsOneWidget);
    expect(find.text('max_of_three'), findsOneWidget);
    expect(find.text('is_palindrome'), findsOneWidget);
    expect(find.textContaining('3 tasks · 2 accepted'), findsOneWidget);
    expect(find.text('seal'), findsOneWidget); // the HashText label
    expect(find.widgetWithText(FilledButton, 'Verify'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Corrupt one byte'), findsOneWidget);
  });

  testWidgets('verify shows a MATCH state', (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    await tester.tap(find.widgetWithText(FilledButton, 'Run eval'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Verify'));
    await tester.pumpAndSettle();
    expect(find.text('MATCH'), findsOneWidget); // the VerdictPill, uppercased
  });

  testWidgets('corrupt one byte flips the seal and the verifier refuses',
      (tester) async {
    Map<String, dynamic>? sawReceipt;
    await tester.pumpWidget(_wrap(_panel(onVerify: (r) async {
      sawReceipt = r;
      return _verify(r);
    })));
    await tester.tap(find.widgetWithText(FilledButton, 'Run eval'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Corrupt one byte'));
    await tester.pumpAndSettle();
    // the panel corrupted a COPY: the seal it verified is not the good one
    expect('${(sawReceipt!['seal'] as Map)['hex']}', isNot(_goodHex));
    // the refusal is a first-class state that NAMES the failing check
    expect(find.textContaining('SEAL_MISMATCH'), findsOneWidget);
    expect(find.textContaining('One flipped byte, refused.'), findsOneWidget);
  });

  testWidgets('verify then corrupt shows both the MATCH and the TAMPERED states',
      (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    await tester.tap(find.widgetWithText(FilledButton, 'Run eval'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Verify'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Corrupt one byte'));
    await tester.pumpAndSettle();
    expect(find.text('MATCH'), findsOneWidget);
    expect(find.textContaining('SEAL_MISMATCH'), findsOneWidget);
  });

  testWidgets('a provider error is stated as an honest null', (tester) async {
    await tester.pumpWidget(_wrap(_panel(
        onRun: () async => {'error': 'no credential present'})));
    await tester.tap(find.widgetWithText(FilledButton, 'Run eval'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Provider error: no credential present'),
        findsOneWidget);
  });
}
