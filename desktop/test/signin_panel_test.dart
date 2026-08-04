// Sign-in in the app does what the engine promises: each provider states its
// own terms, a browser flow starts without asking for a value, a guided flow
// takes the paste in an obscured field and never shows it back, and a machine
// with no credential store says so instead of offering a dead button.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/signin_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Map<String, dynamic> _doc({bool store = true, bool present = false}) => {
      'credential_store': store,
      'note': 'Sign-in stores a token in the OS credential store.',
      'providers': [
        {
          'provider': 'openrouter',
          'kind': 'pkce',
          'kind_label': 'browser sign-in',
          'keychain_name': 'OPENROUTER_API_KEY',
          'present': present,
          'source': present ? 'keychain' : 'absent',
          'sanction': 'documented third-party PKCE flow; no registration required',
          'pending': false,
          'last': '',
          'last_error': '',
        },
        {
          'provider': 'anthropic',
          'kind': 'guided-cli',
          'kind_label': 'provider tool',
          'keychain_name': 'CLAUDE_CODE_OAUTH_TOKEN',
          'present': false,
          'source': 'absent',
          'sanction': 'token minted by the official claude CLI; flywheel runs '
              'no OAuth client of its own',
          'pending': false,
          'last': '',
          'last_error': '',
        },
      ],
    };

SigninPanel _panel(
  Map<String, dynamic> doc, {
  Future<Map<String, dynamic>> Function(String)? onLogin,
  Future<Map<String, dynamic>> Function(String, String)? onToken,
  Future<Map<String, dynamic>> Function(String)? onLogout,
}) =>
    SigninPanel(
      doc: doc,
      onLogin: onLogin ?? (p) async => {'ok': true, 'mode': 'browser'},
      onToken: onToken ?? (p, t) async => {'ok': true, 'stored': 'X'},
      onLogout: onLogout ?? (p) async => {'ok': true},
      onChanged: () {},
    );

void main() {
  testWidgets('every provider states its own terms', (tester) async {
    await tester.pumpWidget(_wrap(_panel(_doc())));
    expect(find.text('openrouter'), findsOneWidget);
    expect(find.text('anthropic'), findsOneWidget);
    expect(find.textContaining('no registration required'), findsOneWidget);
    expect(find.textContaining('runs no OAuth client of its own'), findsOneWidget);
    // the kind is named in the user's words, not the enum's
    expect(find.text('browser sign-in'), findsOneWidget);
    expect(find.text('provider tool'), findsOneWidget);
  });

  testWidgets('a browser sign-in starts without asking for a value',
      (tester) async {
    final calls = <String>[];
    await tester.pumpWidget(_wrap(_panel(_doc(), onLogin: (p) async {
      calls.add(p);
      return {'ok': true, 'mode': 'browser', 'note': 'a browser window is opening'};
    })));
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in').first);
    await tester.pumpAndSettle();
    expect(calls, ['openrouter']);
    expect(find.textContaining('browser window is opening'), findsOneWidget);
    // no field was ever offered for this flow
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('a guided sign-in shows steps and hides the paste',
      (tester) async {
    String? sentToken;
    await tester.pumpWidget(_wrap(_panel(
      _doc(),
      onLogin: (p) async => {
        'ok': true,
        'mode': 'guided',
        'steps': ['Run `claude setup-token`', 'Approve it', 'Paste it below'],
      },
      onToken: (p, t) async {
        sentToken = t;
        return {'ok': true, 'stored': 'CLAUDE_CODE_OAUTH_TOKEN'};
      },
    )));
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in').last);
    await tester.pumpAndSettle();
    expect(find.textContaining('1. Run `claude setup-token`'), findsOneWidget);

    final field = tester.widget<TextField>(find.byType(TextField));
    expect(field.obscureText, isTrue); // never shown back

    await tester.enterText(find.byType(TextField), 'sk-ant-oat-SECRET');
    await tester.tap(find.widgetWithText(FilledButton, 'Store'));
    await tester.pumpAndSettle();
    expect(sentToken, 'sk-ant-oat-SECRET');
    // the value left the widget: the field is gone and the secret is not
    // rendered anywhere on screen
    expect(find.byType(TextField), findsNothing);
    expect(find.textContaining('SECRET'), findsNothing);
    expect(find.textContaining('stored CLAUDE_CODE_OAUTH_TOKEN'), findsOneWidget);
  });

  testWidgets('a signed-in provider offers sign out and names its source',
      (tester) async {
    final out = <String>[];
    await tester.pumpWidget(_wrap(_panel(_doc(present: true),
        onLogout: (p) async {
      out.add(p);
      return {'ok': true};
    })));
    expect(find.textContaining('keychain:OPENROUTER_API_KEY'), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, 'Sign out'));
    await tester.pumpAndSettle();
    expect(out, ['openrouter']);
  });

  testWidgets('no credential store is stated, not hidden', (tester) async {
    await tester.pumpWidget(_wrap(_panel(_doc(store: false))));
    expect(find.textContaining('No OS credential store'), findsOneWidget);
  });

  testWidgets('a pending flow says so instead of offering the button again',
      (tester) async {
    final doc = _doc();
    (doc['providers'] as List)[0]['pending'] = true;
    await tester.pumpWidget(_wrap(_panel(doc)));
    expect(find.textContaining('waiting for the browser'), findsOneWidget);
    // only the guided provider still offers a button
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
  });

  testWidgets('a failed attempt shows its reason', (tester) async {
    final doc = _doc();
    (doc['providers'] as List)[0]['last_error'] =
        'token exchange rejected (HTTP 400)';
    await tester.pumpWidget(_wrap(_panel(doc)));
    expect(find.textContaining('HTTP 400'), findsOneWidget);
  });

  testWidgets('an empty roster is stated, never blank', (tester) async {
    await tester.pumpWidget(_wrap(_panel(
        {'credential_store': true, 'note': '', 'providers': []})));
    expect(find.textContaining('declared no sign-in providers'), findsOneWidget);
  });
}
