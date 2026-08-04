// The signed usage panel does on screen what the engine promises: it reads the
// session roll-up, shows the total spend and a per-answer breakdown with each
// number's provenance (provider_reported / estimated / unpriced_local), and
// VERIFY re-checks one receipt offline — MATCH is the accept mark. An empty
// session is stated as an honest null, not a blank. Faked callbacks, no network.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/usage_receipt_panel.dart';

final _goodHex = List.filled(64, 'a').join();

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Map<String, dynamic> _summary() => {
      'n': '2',
      'total_tokens': {'prompt': '1040', 'completion': '520', 'total': '1560'},
      'priced_total': {'amount': '0.000450', 'currency': 'USD', 'n': '1'},
      'unpriced_count': '1',
      'by_endpoint': {
        'openai': {'n': '1', 'prompt': '1000', 'completion': '500', 'total': '1500'},
        'ollama': {'n': '1', 'prompt': '40', 'completion': '20', 'total': '60'},
      },
      'receipts': [
        {
          'schema': 'flywheel.usage-receipt/v1',
          'endpoint': 'openai',
          'model_ref': 'openai:gpt-4o-mini',
          'tokens': {'prompt': '1000', 'completion': '500', 'total': '1500'},
          'cost': {'amount': '0.000450', 'currency': 'USD', 'note': 'table lookup'},
          'source': 'provider_reported',
          'seal': {'algorithm': 'sha256', 'hex': _goodHex},
        },
        {
          'schema': 'flywheel.usage-receipt/v1',
          'endpoint': 'ollama',
          'model_ref': 'ollama',
          'tokens': {'prompt': '40', 'completion': '20', 'total': '60'},
          'cost': {'amount': '', 'currency': '', 'note': 'no per-token price'},
          'source': 'unpriced_local',
          'seal': {'algorithm': 'sha256', 'hex': _goodHex},
        },
      ],
    };

Map<String, dynamic> _verify(Map<String, dynamic> receipt) {
  final hex = '${(receipt['seal'] as Map)['hex']}';
  if (hex == _goodHex) {
    return {'verdict': 'MATCH', 'failure_class': '', 'detail': '1500 tokens verified'};
  }
  return {'verdict': 'TAMPERED', 'failure_class': 'SEAL_MISMATCH', 'detail': 'refused'};
}

UsageReceiptPanel _panel({
  Future<Map<String, dynamic>> Function()? loadSummary,
  Future<Map<String, dynamic>> Function(Map<String, dynamic>)? onVerify,
}) =>
    UsageReceiptPanel(
      loadSummary: loadSummary ?? (() async => _summary()),
      onVerify: onVerify ?? ((r) async => _verify(r)),
    );

void main() {
  testWidgets('an empty session is stated as an honest null', (tester) async {
    await tester.pumpWidget(_wrap(_panel(
        loadSummary: () async => {'n': '0', 'receipts': [], 'unpriced_count': '0'})));
    await tester.pumpAndSettle();
    expect(find.textContaining('No usage receipts yet'), findsOneWidget);
  });

  testWidgets('an offline summary degrades to an honest null', (tester) async {
    await tester.pumpWidget(_wrap(_panel(
        loadSummary: () async => {'error': 'engine offline'})));
    await tester.pumpAndSettle();
    expect(find.textContaining('engine offline'), findsOneWidget);
  });

  testWidgets('the totals and per-answer provenance render', (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    await tester.pumpAndSettle();
    expect(find.text('1560'), findsOneWidget); // total tokens tile
    // the priced total tile AND the one priced receipt row both show it
    expect(find.text('USD 0.000450'), findsWidgets); // priced total (table)
    expect(find.text('provider_reported'), findsOneWidget);
    expect(find.text('unpriced_local'), findsOneWidget);
    expect(find.textContaining('openai'), findsWidgets);
  });

  testWidgets('verifying a receipt shows a MATCH state', (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    await tester.pumpAndSettle();
    // tapping a receipt row verifies it offline
    await tester.tap(find.text('provider_reported'));
    await tester.pumpAndSettle();
    expect(find.text('MATCH'), findsOneWidget); // the VerdictPill, uppercased
  });

  testWidgets('a refresh re-reads the summary', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_wrap(_panel(loadSummary: () async {
      calls++;
      return _summary();
    })));
    await tester.pumpAndSettle();
    expect(calls, 1); // initial load
    await tester.tap(find.widgetWithText(TextButton, 'Refresh'));
    await tester.pumpAndSettle();
    expect(calls, 2);
  });
}
