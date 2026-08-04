// The audit panel does on screen what the engine promises: paste a sealed work
// receipt, RUN AUDIT reviews it and seals an audit receipt CHAINED onto the work;
// VERIFY shows MATCH plus the chain link back to the work; and CORRUPT ONE BYTE
// flips a single hex char of a COPY of the audit receipt and re-verifies THAT —
// the same verifier refuses and NAMES the failing check, while the stored receipt
// is never touched. Faked callbacks, no network.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/audit_receipt_panel.dart';

final _goodHex = List.filled(64, 'a').join(); // a well-formed 64-hex seal
final _workHex = List.filled(64, 'b').join(); // the work receipt's seal hex

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

// A sealed work receipt, as JSON the user would paste.
const _workReceiptJson = '{"schema":"flywheel.tool-call-receipt/v1",'
    '"seal":{"algorithm":"sha256","hex":'
    '"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}';

Map<String, dynamic> _runDoc() => {
      'verdict': 'CONCERNS',
      'confidence': 'moderate',
      'summary': 'verdict CONCERNS over 2 review(s).',
      'does_not_prove': 'a cheap post-work review, not a proof.',
      'reviews': [
        {
          'detector_id': 'receipt_integrity',
          'dimension': 'correctness',
          'severity': 'INFO',
          'summary': 'the work receipt seal re-derives; the record is intact'
        },
        {
          'detector_id': 'honest_null_presence',
          'dimension': 'completeness',
          'severity': 'WARN',
          'summary': 'the work product reports a result but states no honest-null'
        },
      ],
      'receipt': {
        'schema': 'flywheel.audit-receipt/v1',
        'prev_receipt_sha256': _workHex,
        'seal': {'algorithm': 'sha256', 'hex': _goodHex},
      },
    };

// A faithful fake verifier: the good seal is MATCH, anything else is refused
// with a named failure class — exactly what the offline verifier does.
Map<String, dynamic> _verify(Map<String, dynamic> receipt) {
  final hex = '${(receipt['seal'] as Map)['hex']}';
  if (hex == _goodHex) {
    return {
      'verdict': 'MATCH',
      'failure_class': '',
      'detail': '2 review(s), verdict CONCERNS; chained to sha256:bbbbbbbbbbbb'
    };
  }
  return {
    'verdict': 'TAMPERED',
    'failure_class': 'SEAL_MISMATCH',
    'detail': 'seal sha256:aaaaaaaaaaaa, recomputed sha256:0badbadbad00',
  };
}

AuditReceiptPanel _panel({
  Future<Map<String, dynamic>> Function(Map<String, dynamic>)? onRun,
  Future<Map<String, dynamic>> Function(
          Map<String, dynamic>, Map<String, dynamic>?)?
      onVerify,
}) =>
    AuditReceiptPanel(
      onRun: onRun ?? ((_) async => _runDoc()),
      onVerify: onVerify ?? ((r, _) async => _verify(r)),
    );

Future<void> _pasteAndRun(WidgetTester tester) async {
  await tester.enterText(find.byType(TextField), _workReceiptJson);
  await tester.tap(find.widgetWithText(FilledButton, 'Run audit'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('no audit yet is stated, not blank', (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    expect(find.textContaining('No audit yet'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Run audit'), findsOneWidget);
  });

  testWidgets('a run seals an audit: reviews, verdict, and seal hex show',
      (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    await _pasteAndRun(tester);
    expect(find.text('correctness'), findsOneWidget);
    expect(find.text('completeness'), findsOneWidget);
    expect(find.textContaining('confidence moderate'), findsOneWidget);
    expect(find.text('seal'), findsOneWidget); // the HashText label
    expect(find.textContaining('not a proof'), findsOneWidget); // does_not_prove
    expect(find.widgetWithText(FilledButton, 'Verify'), findsOneWidget);
    expect(
        find.widgetWithText(OutlinedButton, 'Corrupt one byte'), findsOneWidget);
  });

  testWidgets('a bad work receipt is stated as an honest null', (tester) async {
    await tester.pumpWidget(_wrap(_panel()));
    await tester.enterText(find.byType(TextField), 'not json at all');
    await tester.tap(find.widgetWithText(FilledButton, 'Run audit'));
    await tester.pumpAndSettle();
    expect(find.textContaining('not valid JSON'), findsOneWidget);
  });

  testWidgets('verify shows MATCH and the chain link to the work receipt',
      (tester) async {
    Map<String, dynamic>? sawWork;
    await tester.pumpWidget(_wrap(_panel(onVerify: (r, w) async {
      sawWork = w;
      return _verify(r);
    })));
    await _pasteAndRun(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Verify'));
    await tester.pumpAndSettle();
    expect(find.text('MATCH'), findsOneWidget); // the VerdictPill, uppercased
    // the chain-link line names the work receipt the audit binds to
    expect(find.textContaining('chain → work receipt'), findsOneWidget);
    // the panel handed the work receipt to the verifier for the chain check
    expect(sawWork, isNotNull);
    expect('${(sawWork!['seal'] as Map)['hex']}', _workHex);
  });

  testWidgets('corrupt one byte flips the seal and the verifier refuses',
      (tester) async {
    Map<String, dynamic>? sawReceipt;
    await tester.pumpWidget(_wrap(_panel(onVerify: (r, w) async {
      sawReceipt = r;
      return _verify(r);
    })));
    await _pasteAndRun(tester);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Corrupt one byte'));
    await tester.pumpAndSettle();
    // the panel corrupted a COPY: the seal it verified is not the good one
    expect('${(sawReceipt!['seal'] as Map)['hex']}', isNot(_goodHex));
    // the refusal is a first-class state that NAMES the failing check
    expect(find.textContaining('SEAL_MISMATCH'), findsOneWidget);
    expect(find.textContaining('One flipped byte, refused.'), findsOneWidget);
  });
}
