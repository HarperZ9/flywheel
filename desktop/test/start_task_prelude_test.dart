import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_mode_pane.dart';
import 'package:flywheel_desktop/widgets/start_task_prelude.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Widget _host(Widget child,
    {Size size = const Size(720, 640), double textScale = 1}) {
  return MaterialApp(
    theme: flywheelLightTheme(),
    home: MediaQuery(
      data:
          MediaQueryData(size: size, textScaler: TextScaler.linear(textScale)),
      child: Scaffold(body: SizedBox.fromSize(size: size, child: child)),
    ),
  );
}

EndpointRow _endpoint({
  String name = 'claude-cli',
  String credential = 'cli-auth',
  bool accountAuthenticated = true,
}) =>
    EndpointRow(
      name: name,
      backend: name == 'local-public' ? 'local' : 'hosted',
      credential: credential,
      providerRole: name == 'local-public' ? 'local' : 'assistant',
      configured: true,
      accountAuthenticated: accountAuthenticated,
    );

Future<void> _pumpPrelude(
  WidgetTester tester, {
  List<EndpointRow>? endpoints,
  String? endpoint = 'claude-cli',
  String? chosenModel,
  Future<PromptDisposition> Function(String text)? onSend,
  VoidCallback? onOpenModels,
  ValueChanged<String>? onUseWorkspace,
  Size size = const Size(720, 640),
  double textScale = 1,
}) async {
  await tester.pumpWidget(_host(
    StartTaskPrelude(
      endpoints: endpoints ?? [_endpoint()],
      endpoint: endpoint,
      chosenModel: chosenModel,
      streaming: false,
      initialText: '',
      onDraftChanged: (_) {},
      onSend: onSend ?? (_) async => PromptDisposition.accepted,
      onEndpoint: (_) {},
      onModel: (_) {},
      loadModels: () async => const {},
      onOpenModels: onOpenModels,
      onUseWorkspaceGoal: onUseWorkspace,
    ),
    size: size,
    textScale: textScale,
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('prelude keeps a plain task primary and reports selected route',
      (tester) async {
    final sent = <String>[];
    await _pumpPrelude(
      tester,
      chosenModel: 'opus',
      onSend: (text) async {
        sent.add(text);
        return PromptDisposition.accepted;
      },
    );

    expect(find.text('What do you want Flywheel to do?'), findsOneWidget);
    expect(find.text('claude-cli'), findsOneWidget);
    expect(find.text('opus'), findsOneWidget);
    expect(find.text('Subscription access'), findsOneWidget);
    expect(find.text('Cost not reported by this route.'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('start-task-input')),
        'Summarize the receipts from yesterday.');
    await tester.pump();
    await tester.tap(find.byKey(const Key('start-task-primary')));
    await tester.pumpAndSettle();

    expect(sent, ['Summarize the receipts from yesterday.']);
  });

  testWidgets('prelude routes unavailable model state to setup without sending',
      (tester) async {
    final sent = <String>[];
    var openedModels = 0;
    await _pumpPrelude(
      tester,
      endpoints: const [],
      endpoint: null,
      onOpenModels: () => openedModels++,
      onSend: (text) async {
        sent.add(text);
        return PromptDisposition.accepted;
      },
    );

    expect(find.text('No model route selected.'), findsOneWidget);
    await tester.enterText(
        find.byKey(const Key('start-task-input')), 'Compare two drafts.');
    await tester.pump();
    await tester.tap(find.byKey(const Key('start-task-primary')));
    await tester.pumpAndSettle();

    expect(openedModels, 1);
    expect(sent, isEmpty);
  });

  testWidgets(
      'prelude requires an explicit workspace choice and preserves goal',
      (tester) async {
    final goals = <String>[];
    await _pumpPrelude(tester, onUseWorkspace: goals.add);

    expect(find.textContaining('Workspace tasks use Agent mode'), findsNothing);
    await tester.enterText(find.byKey(const Key('start-task-input')),
        'Update the project README after checking tests.');
    await tester.pump();
    await tester.tap(find.byKey(const Key('start-task-workspace-toggle')));
    await tester.pumpAndSettle();

    expect(
        find.textContaining('Workspace tasks use Agent mode'), findsOneWidget);
    await tester
        .ensureVisible(find.byKey(const Key('start-task-use-workspace')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('start-task-use-workspace')));
    await tester.pumpAndSettle();

    expect(goals, ['Update the project README after checking tests.']);
  });

  testWidgets('prelude sends by keyboard and keeps controls at least 44px',
      (tester) async {
    final sent = <String>[];
    await _pumpPrelude(
      tester,
      size: const Size(520, 520),
      textScale: 1.4,
      onUseWorkspace: (_) {},
      onSend: (text) async {
        sent.add(text);
        return PromptDisposition.accepted;
      },
    );

    await tester.enterText(find.byKey(const Key('start-task-input')),
        'Find the duplicated section links.');
    await tester.pump();
    await tester.tap(find.byKey(const Key('start-task-input')));
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();

    expect(sent, ['Find the duplicated section links.']);
    for (final key in const [
      Key('start-task-primary'),
      Key('start-task-model-picker'),
      Key('start-task-workspace-toggle'),
    ]) {
      final size = tester.getSize(find.byKey(key));
      expect(size.width, greaterThanOrEqualTo(44), reason: '$key width');
      expect(size.height, greaterThanOrEqualTo(44), reason: '$key height');
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('prelude does not submit while IME composition is active',
      (tester) async {
    final sent = <String>[];
    await _pumpPrelude(
      tester,
      onSend: (text) async {
        sent.add(text);
        return PromptDisposition.accepted;
      },
    );

    final input = find.byKey(const Key('start-task-input'));
    await tester.enterText(input, 'nihon');
    await tester.tap(input);
    await tester.pump();
    final editable = tester.widget<EditableText>(find.byType(EditableText));
    editable.controller.value = const TextEditingValue(
      text: 'nihon',
      selection: TextSelection.collapsed(offset: 5),
      composing: TextRange(start: 0, end: 5),
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();

    expect(sent, isEmpty);
    expect(editable.controller.text, 'nihon');
  });

  testWidgets('prelude inserts newline on Shift Enter without submitting',
      (tester) async {
    final sent = <String>[];
    await _pumpPrelude(
      tester,
      onSend: (text) async {
        sent.add(text);
        return PromptDisposition.accepted;
      },
    );

    final input = find.byKey(const Key('start-task-input'));
    await tester.enterText(input, 'Line one');
    await tester.tap(input);
    await tester.pump();
    final before = tester.widget<EditableText>(find.byType(EditableText));
    before.controller.selection =
        const TextSelection.collapsed(offset: 'Line one'.length);
    await tester.sendKeyDownEvent(LogicalKeyboardKey.shiftLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.shiftLeft);
    await tester.pump();

    final editable = tester.widget<EditableText>(find.byType(EditableText));
    expect(sent, isEmpty);
    expect(editable.controller.text, 'Line one\n');
  });

  testWidgets('agent workspace handoff seeds the existing agent composer',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('flywheel-agent-seed-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final client = GatewayClient(
      baseUrl: 'https://agent.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(jsonEncode({'rows': []}), 200);
        }
        return http.Response('{}', 200);
      }),
    );

    await tester.pumpWidget(_host(AgentModePane(
      client: client,
      alive: true,
      settings: DesktopSettings(),
      initialGoal: 'Refactor the onboarding copy.',
    )));
    await tester.pumpAndSettle();

    await tester.enterText(
        find.byKey(const Key('agent-mode-root-field')), dir.path);
    await tester.tap(find.byKey(const Key('agent-mode-use-root')));
    await tester.pumpAndSettle();

    expect(find.text('Refactor the onboarding copy.'), findsOneWidget);
  });
}
