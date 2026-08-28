// Session tokens panel: an empty roster states it honestly; an active token
// shows its session ref and slot count but NEVER its token_ref value; revoke
// calls back with the token_ref so the caller can hit the gateway route.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/session_tokens_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Map<String, dynamic> _doc({List<Map<String, dynamic>>? tokens}) => {
      'ok': true,
      'tokens': tokens ?? [],
    };

void main() {
  testWidgets('empty tokens states it honestly', (tester) async {
    await tester.pumpWidget(_wrap(SessionTokensPanel(
      doc: _doc(),
      onRevoke: (_) async => {'ok': true},
      onChanged: () {},
    )));
    expect(find.textContaining('No active session tokens'), findsOneWidget);
  });

  testWidgets('active tokens show session ref and slot count', (tester) async {
    await tester.pumpWidget(_wrap(SessionTokensPanel(
      doc: _doc(tokens: [
        {'token_ref': 'stok_abc', 'session_ref': 'sess_001',
         'slots': 2, 'expires_at': DateTime.now()
             .add(const Duration(minutes: 10))
             .millisecondsSinceEpoch / 1000},
      ]),
      onRevoke: (_) async => {'ok': true},
      onChanged: () {},
    )));
    expect(find.textContaining('sess_001'), findsOneWidget);
    expect(find.textContaining('2 slots'), findsOneWidget);
  });

  testWidgets('revoke button calls onRevoke with token_ref', (tester) async {
    String? revokedRef;
    await tester.pumpWidget(_wrap(SessionTokensPanel(
      doc: _doc(tokens: [
        {'token_ref': 'stok_abc', 'session_ref': 'sess_001',
         'slots': 1, 'expires_at': DateTime.now()
             .add(const Duration(minutes: 10))
             .millisecondsSinceEpoch / 1000},
      ]),
      onRevoke: (ref) async { revokedRef = ref; return {'ok': true}; },
      onChanged: () {},
    )));
    await tester.tap(find.widgetWithText(TextButton, 'Revoke'));
    await tester.pumpAndSettle();
    expect(revokedRef, 'stok_abc');
  });

  testWidgets('token_ref value is never displayed', (tester) async {
    await tester.pumpWidget(_wrap(SessionTokensPanel(
      doc: _doc(tokens: [
        {'token_ref': 'stok_abc123def456', 'session_ref': 'sess_001',
         'slots': 1, 'expires_at': DateTime.now()
             .add(const Duration(minutes: 10))
             .millisecondsSinceEpoch / 1000},
      ]),
      onRevoke: (_) async => {'ok': true},
      onChanged: () {},
    )));
    expect(find.textContaining('stok_abc123def456'), findsNothing);
  });
}
