import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/fw.dart';
import 'package:flywheel_desktop/widgets/signin_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
  theme: flywheelLightTheme(),
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

Map<String, dynamic> _doc({
  bool store = true,
  bool present = false,
  String last = '',
}) => {
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
      'last': last,
      'last_error': '',
    },
  ],
};

SigninPanel _panel(
  Map<String, dynamic> doc, {
  Future<Map<String, dynamic>> Function(String)? onLogin,
  Future<Map<String, dynamic>> Function(String, String)? onToken,
  Future<Map<String, dynamic>> Function(String)? onLogout,
  Future<bool> Function(String)? onOpenUrl,
}) => SigninPanel(
  doc: doc,
  onLogin: onLogin ?? (p) async => {'ok': true, 'mode': 'browser'},
  onToken: onToken ?? (p, t) async => {'ok': true, 'stored': 'X'},
  onLogout: onLogout ?? (p) async => {'ok': true},
  onOpenUrl: onOpenUrl,
  onChanged: () {},
);

void main() {
  testWidgets(
    'a present credential is labeled unverified and never gets a verified dot',
    (tester) async {
      await tester.pumpWidget(_wrap(_panel(_doc(present: true, last: 'done'))));

      final dot = tester.widget<VerdictDot>(find.byType(VerdictDot));
      expect(dot.status, 'unverifiable');
      expect(find.text('credential stored'), findsOneWidget);
      expect(
        find.text('credential present; authentication unverified'),
        findsOneWidget,
      );
      expect(find.textContaining('signed in'), findsNothing);
    },
  );

  testWidgets('an absent credential remains an ordinary sign-in offer', (
    tester,
  ) async {
    await tester.pumpWidget(_wrap(_panel(_doc())));

    final dot = tester.widget<VerdictDot>(find.byType(VerdictDot));
    expect(dot.status, 'unverifiable');
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
    expect(
      find.text('credential present; authentication unverified'),
      findsNothing,
    );
  });

  testWidgets(
    'successful token storage reports stored but authentication unverified',
    (tester) async {
      await tester.pumpWidget(
        _wrap(
          _panel(
            _doc(),
            onLogin: (provider) async => {
              'ok': true,
              'mode': 'guided',
              'steps': ['Run the provider tool', 'Paste below'],
            },
            onToken: (provider, token) async => {
              'ok': true,
              'stored': 'CLAUDE_CODE_OAUTH_TOKEN',
            },
          ),
        ),
      );

      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'sk-ant-oat-synthetic');
      await tester.tap(find.widgetWithText(FilledButton, 'Store'));
      await tester.pumpAndSettle();

      expect(
        find.text(
          'credential stored CLAUDE_CODE_OAUTH_TOKEN; authentication unverified',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('signed in'), findsNothing);
      expect(find.textContaining('sk-ant-oat-synthetic'), findsNothing);
    },
  );

  testWidgets('failed token storage still reports the store failure', (
    tester,
  ) async {
    await tester.pumpWidget(
      _wrap(
        _panel(
          _doc(),
          onLogin: (provider) async => {
            'ok': true,
            'mode': 'guided',
            'steps': ['Run the provider tool', 'Paste below'],
          },
          onToken: (provider, token) async => {
            'ok': false,
            'error':
                'token obtained but NOT stored: credential store write failed',
          },
        ),
      ),
    );

    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'sk-ant-oat-synthetic');
    await tester.tap(find.widgetWithText(FilledButton, 'Store'));
    await tester.pumpAndSettle();

    expect(find.textContaining('NOT stored'), findsOneWidget);
    expect(
      find.text(
        'credential stored CLAUDE_CODE_OAUTH_TOKEN; authentication unverified',
      ),
      findsNothing,
    );
    expect(find.textContaining('sk-ant-oat-synthetic'), findsNothing);
  });
}
