import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/signin_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Map<String, dynamic> _chatgptProvider({
  bool present = false,
  bool pending = false,
  String last = '',
  String lastError = '',
  bool routeReady = false,
  bool readinessCheckAvailable = false,
  String routeReadyReason = '',
}) =>
    {
      'provider': 'openai',
      'kind': 'official-app-server',
      'kind_label': 'ChatGPT account',
      'keychain_name': '',
      'present': present,
      'source': 'codex-app-server',
      'sanction': 'Codex app-server owns ChatGPT account sign-in.',
      'pending': pending,
      'last': last,
      'last_error': lastError,
      'official_app_server': {
        'state': present ? 'authenticated' : 'not_authenticated',
        'account_state': present ? 'authenticated' : 'not_authenticated',
        'authenticated': present,
        'source': 'codex-app-server',
        'plan_type': present ? 'plus' : '',
        'route_ready': routeReady,
        'route_ready_reason': routeReadyReason,
        'run_ready': false,
        'run_ready_reason': '',
        'supervised_run_ready': false,
        'readiness_check_available': readinessCheckAvailable,
      },
    };

Map<String, dynamic> _chatgptDoc({
  bool present = false,
  bool pending = false,
  String last = '',
  String lastError = '',
  bool routeReady = false,
  bool readinessCheckAvailable = false,
  String routeReadyReason = '',
}) =>
    {
      'credential_store': true,
      'note': 'Values are never displayed.',
      'providers': [
        _chatgptProvider(
          present: present,
          pending: pending,
          last: last,
          lastError: lastError,
          routeReady: routeReady,
          readinessCheckAvailable: readinessCheckAvailable,
          routeReadyReason: routeReadyReason,
        ),
      ],
    };

SigninPanel _panel(
  Map<String, dynamic> doc, {
  Future<Map<String, dynamic>> Function(String)? onLogin,
  Future<Map<String, dynamic>> Function(String, String)? onToken,
  Future<Map<String, dynamic>> Function(String)? onLogout,
  Future<Map<String, dynamic>> Function(String)? onCancel,
  Future<Map<String, dynamic>> Function(String)? onCheckExecution,
  Future<bool> Function(String)? onOpenUrl,
}) =>
    SigninPanel(
      key: const Key('signin'),
      doc: doc,
      onLogin: onLogin ?? (p) async => {'ok': true, 'mode': 'browser'},
      onToken: onToken ?? (p, t) async => {'ok': true, 'stored': 'X'},
      onLogout: onLogout ?? (p) async => {'ok': true},
      onCancel: onCancel,
      onCheckExecution: onCheckExecution,
      onOpenUrl: onOpenUrl,
      onChanged: () {},
    );

Future<void> _startDeviceCode(WidgetTester tester,
    {Future<Map<String, dynamic>> Function(String)? onCancel}) async {
  await tester.pumpWidget(_wrap(_panel(
    _chatgptDoc(),
    onLogin: (p) async => {
      'ok': true,
      'provider': p,
      'mode': 'device-code',
      'verification_url': 'https://chatgpt.com/activate',
      'user_code': 'SYNTH-1234',
    },
    onCancel: onCancel,
    onOpenUrl: (_) async => true,
  )));
  await tester.tap(find.widgetWithText(FilledButton, 'Open sign-in'));
  await tester.pumpAndSettle();
  expect(find.text('Code: SYNTH-1234'), findsOneWidget);
}

void main() {
  testWidgets('completed account clears previous device code and Cancel',
      (tester) async {
    await _startDeviceCode(tester, onCancel: (p) async => {'ok': true});

    await tester.pumpWidget(_wrap(_panel(_chatgptDoc(present: true))));
    await tester.pumpAndSettle();

    expect(find.textContaining('ChatGPT account connected'), findsOneWidget);
    expect(find.text('Code: SYNTH-1234'), findsNothing);
    expect(find.widgetWithText(TextButton, 'Cancel'), findsNothing);
  });

  testWidgets('failed cancellation preserves usable device code',
      (tester) async {
    await _startDeviceCode(
      tester,
      onCancel: (p) async => {
        'ok': false,
        'error': 'cancel refused; sign-in is still pending',
      },
    );

    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(find.textContaining('cancel refused'), findsOneWidget);
    expect(find.text('Code: SYNTH-1234'), findsOneWidget);
    expect(find.widgetWithText(TextButton, 'Cancel'), findsOneWidget);
  });

  testWidgets('connected phone-width account row has no overflow',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;

    await tester.pumpWidget(_wrap(_panel(_chatgptDoc(present: true))));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets('pending phone-width device login row has no overflow',
      (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;

    await tester.pumpWidget(_wrap(_panel(
      _chatgptDoc(pending: true),
      onCancel: (p) async => {'ok': true},
    )));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });

  testWidgets('route check renders refreshed provider reason', (tester) async {
    await tester.pumpWidget(_wrap(_panel(
      _chatgptDoc(present: true, readinessCheckAvailable: true),
      onCheckExecution: (p) async => _chatgptDoc(
        present: true,
        readinessCheckAvailable: true,
        routeReadyReason: 'codex exec help exited 2',
      ),
    )));

    await tester.tap(find.widgetWithText(TextButton, 'Check route'));
    await tester.pumpAndSettle();

    expect(find.textContaining('codex exec help exited 2'), findsOneWidget);
    final check = find.widgetWithText(TextButton, 'Check route');
    expect(tester.widget<TextButton>(check).onPressed, isNotNull);
  });

  testWidgets('route check has a UI watchdog and recovers controls',
      (tester) async {
    final checkRead = Completer<Map<String, dynamic>>();
    var checks = 0;
    await tester.pumpWidget(_wrap(_panel(
      _chatgptDoc(present: true, readinessCheckAvailable: true),
      onCheckExecution: (p) {
        checks += 1;
        return checkRead.future;
      },
    )));

    final check = find.widgetWithText(TextButton, 'Check route');
    await tester.tap(check);
    await tester.pump();
    expect(checks, 1);
    expect(tester.widget<TextButton>(check).onPressed, isNull);

    await tester.pump(const Duration(seconds: 21));
    await tester.pump();

    expect(find.textContaining('route check timed out'), findsOneWidget);
    expect(tester.widget<TextButton>(check).onPressed, isNull);
    expect(
        tester
            .widget<TextButton>(find.widgetWithText(TextButton, 'Sign out'))
            .onPressed,
        isNotNull);
    await tester.tap(check);
    await tester.pump();
    expect(checks, 1);

    checkRead.complete(_chatgptDoc(
      present: true,
      routeReady: true,
      readinessCheckAvailable: true,
    ));
    await tester.pumpAndSettle();

    expect(find.textContaining('route check passed'), findsOneWidget);
    expect(tester.widget<TextButton>(check).onPressed, isNotNull);
  });
}
