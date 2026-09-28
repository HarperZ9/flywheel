import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/codex_account_client.dart';
import 'package:flywheel_desktop/controllers/codex_account_controller.dart';
import 'package:flywheel_desktop/models/codex_account_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/codex_account_panel.dart';

void main() {
  testWidgets('panel opens returned browser URL only after explicit tap',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final opened = <Uri>[];
    final api = _PanelApi(_signedOut())
      ..start = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'browser',
        'login_id': 'login_ui',
        'auth_url': 'https://chatgpt.com/auth/codex',
      });
    final controller = CodexAccountController(api);

    await tester.pumpWidget(_wrap(CodexAccountPanel(
      controller: controller,
      openUrl: (uri) async {
        opened.add(uri);
        return true;
      },
      onAccountReady: () {},
    )));
    await tester.pumpAndSettle();
    await tester
        .tap(find.widgetWithText(FilledButton, 'Start browser sign-in'));
    await tester.pumpAndSettle();

    expect(opened, isEmpty);
    expect(find.byType(TextField), findsNothing);
    expect(find.text('login_ui'), findsOneWidget);
    await tester.tap(find.widgetWithText(OutlinedButton, 'Open returned URL'));
    await tester.pumpAndSettle();
    expect(opened.single.toString(), 'https://chatgpt.com/auth/codex');
  });

  testWidgets('device-code flow shows code and cancel without token input',
      (tester) async {
    final api = _PanelApi(_signedOut())
      ..start = CodexLoginStart.fromJson({
        'state': 'login_started',
        'mode': 'device_code',
        'login_id': 'login_device',
        'verification_url': 'https://openai.com/device',
        'user_code': 'ABCD-EFGH',
      });
    final controller = CodexAccountController(api);

    await tester.pumpWidget(_wrap(CodexAccountPanel(
      controller: controller,
      openUrl: (_) async => true,
      onAccountReady: () {},
    )));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Use device code'));
    await tester.pumpAndSettle();

    expect(find.text('ABCD-EFGH'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);
    await tester.tap(find.widgetWithText(TextButton, 'Cancel login'));
    await tester.pumpAndSettle();
    expect(api.cancelled, ['login_device']);
  });

  testWidgets('signed-in panel distinguishes subscription from API billing',
      (tester) async {
    final api = _PanelApi(_apiAndChatGpt())
      ..catalog = CodexModelCatalog.fromJson({
        'allow_manual': false,
        'listing_authoritative': true,
        'models': [
          {'id': 'gpt-5.6-sol'},
        ],
      });
    final controller = CodexAccountController(api);

    await tester.pumpWidget(_wrap(CodexAccountPanel(
      controller: controller,
      openUrl: (_) async => true,
      onAccountReady: () {},
    )));
    await tester.pumpAndSettle();

    expect(find.text('OpenAI API billing route'), findsOneWidget);
    expect(find.text('ChatGPT Plus account ready'), findsOneWidget);
    expect(find.textContaining('gpt-5.6-sol'), findsOneWidget);
  });

  testWidgets('primary actions keep a 44dp floor under text scaling',
      (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(() => tester.platformDispatcher.textScaleFactorTestValue = 1.0);
    final controller = CodexAccountController(_PanelApi(_signedOut()));

    await tester.pumpWidget(_wrap(CodexAccountPanel(
      controller: controller,
      openUrl: (_) async => true,
      onAccountReady: () {},
    )));
    await tester.pumpAndSettle();

    for (final entry in [
      (FilledButton, 'Start browser sign-in'),
      (OutlinedButton, 'Use device code'),
    ]) {
      final finder = find.widgetWithText(entry.$1, entry.$2);
      expect(finder, findsOneWidget);
      final box = tester.renderObject<RenderBox>(finder);
      expect(box.size.height, greaterThanOrEqualTo(44));
    }
  });
}

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

CodexAccountDoc _signedOut() => CodexAccountDoc.fromJson({
      'state': 'ready',
      'account': {
        'consumer': {'state': 'not_authenticated'},
        'api_key': {'state': 'absent'},
        'effective_auth_source': 'none',
        'usable_for_codex': false,
      },
    });

CodexAccountDoc _apiAndChatGpt() => CodexAccountDoc.fromJson({
      'state': 'ready',
      'account': {
        'consumer': {
          'state': 'authenticated',
          'type': 'chatgpt',
          'plan_type': 'plus',
        },
        'api_key': {'state': 'present'},
        'effective_auth_source': 'api-key',
        'usable_for_codex': true,
      },
    });

class _PanelApi implements CodexAccountApi {
  _PanelApi(this.account);
  CodexAccountDoc account;
  CodexLoginStart start = CodexLoginStart.fromJson({});
  CodexModelCatalog catalog = CodexModelCatalog.empty();
  final cancelled = <String>[];

  @override
  Future<CodexAccountDoc> readAccount() async => account;

  @override
  Future<CodexLoginStart> startLogin(CodexLoginMode mode) async => start;

  @override
  Future<CodexLoginResult> loginResult(String loginId) async =>
      CodexLoginResult.fromJson({'state': 'pending', 'login_id': loginId});

  @override
  Future<CodexLoginResult> cancelLogin(String loginId) async {
    cancelled.add(loginId);
    return CodexLoginResult.fromJson({'state': 'canceled'});
  }

  @override
  Future<CodexLoginResult> logout() async =>
      CodexLoginResult.fromJson({'state': 'logout_requested'});

  @override
  Future<CodexModelCatalog> readModelCatalog() async => catalog;
}
