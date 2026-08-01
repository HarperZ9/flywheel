// The two new destinations render from real document shapes: the register
// shows presence honestly (a rotted instrument reads absent), the academy
// shows the arc with prereqs, runnable checks, and attribution.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/academy_view.dart';
import 'package:flywheel_desktop/views/instruments_view.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('the register renders live and rotted instruments honestly',
      (tester) async {
    await tester.pumpWidget(_wrap(InstrumentList(const {
      'instruments': [
        {
          'name': 'oracle_strength',
          'present': true,
          'summary': '0 hard flags, 96/110 clean',
          'receipt': 'artifacts/audit/oracle_strength_x.json'
        },
        {
          'name': 'sealed_claims',
          'present': false,
          'summary': 'no sealed claims on record',
          'receipt': ''
        },
      ],
      'present_count': 1,
      'total': 2,
      'note': 'if the instruments rot, the register says so',
    })));
    expect(find.textContaining('oracle_strength'), findsWidgets);
    expect(find.textContaining('96/110 clean'), findsOneWidget);
    expect(find.textContaining('no sealed claims'), findsOneWidget);
    expect(find.textContaining('1/2'), findsOneWidget);
    expect(find.textContaining('rot'), findsOneWidget);
  });

  testWidgets('the academy renders the arc with prereqs and checks',
      (tester) async {
    await tester.pumpWidget(_wrap(AcademyArc({
      'lessons': [
        {
          'id': 'store',
          'title': 'The verifiable substrate',
          'prereqs': [],
          'present': true,
          'teach': 'Store an entity; the receipt is its content hash.',
          'check': {
            'method': 'GET',
            'path': '/api/store/verify',
            'expect': 'ok is true'
          },
          'source_sha256': 'abababababababababababababababab',
        },
        {
          'id': 'loops',
          'title': 'The closed loop, measured',
          'prereqs': ['store'],
          'present': true,
          'teach': 'Every handoff executed, every handoff receipted.',
          'check': {
            'method': 'GET',
            'path': '/api/loops',
            'expect': 'closed_count equals total'
          },
          'source_sha256': 'cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd',
        },
      ],
      'completion_flow': 'teach-back via /api/explain, retest via '
          '/api/retention',
      'attribution': 'abstraction-first shape: Zachary Huang (MIT)',
    })));
    expect(find.textContaining('1. The verifiable substrate'), findsOneWidget);
    expect(find.textContaining('2. The closed loop'), findsOneWidget);
    expect(find.textContaining('<- store'), findsOneWidget);
    expect(find.textContaining('/api/store/verify'), findsOneWidget);
    expect(find.textContaining('/api/explain'), findsOneWidget);
    expect(find.textContaining('Zachary Huang'), findsOneWidget);
  });
}
