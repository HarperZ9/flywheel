import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/navigation/app_route.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/shell/view_factory.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:flywheel_desktop/views/code_view.dart';
import 'package:flywheel_desktop/views/journey_view.dart';
import 'package:flywheel_desktop/widgets/flywheel_nav.dart';
import 'package:flywheel_desktop/widgets/start_task_prelude.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'journey_shell_harness.dart';

Widget _host(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SizedBox(width: 900, height: 720, child: child)),
    );

final class _ChatHarness {
  _ChatHarness() {
    directory = Directory.systemTemp.createTempSync('start-task-handoff-');
    history = ChatStore(file: File('${directory.path}/history.json'));
    drafts = ChatDraftStore(file: File('${directory.path}/drafts.json'));
    client = GatewayClient(
      baseUrl: 'https://chat.invalid',
      httpClient: MockClient((request) async {
        if (request.url.path == '/api/endpoints') {
          return http.Response(
              jsonEncode({
                'rows': [
                  {
                    'name': 'local',
                    'backend': 'local',
                    'credential': 'local-none',
                    'provider_role': 'local',
                    'configured': true,
                  }
                ]
              }),
              200);
        }
        providerCalls++;
        return http.Response('{}', 200);
      }),
    );
  }

  late final Directory directory;
  late final ChatStore history;
  late final ChatDraftStore drafts;
  late final GatewayClient client;
  final settings = DesktopSettings();
  var providerCalls = 0;

  Widget chat({StartTaskHandoff? handoff}) => _host(AgentView(
        client: client,
        alive: true,
        settings: settings,
        chatStore: history,
        draftStore: drafts,
        startTaskHandoff: handoff,
      ));

  List<String> draftTexts() => drafts.load().map((d) => d.text).toList();

  void dispose() => directory.deleteSync(recursive: true);
}

void _prepareDirtyCode(ShellHarness harness) {
  final root = Directory('${harness.directory.path}/workspace')..createSync();
  final file = File('${root.path}/lib/main.dart')
    ..parent.createSync(recursive: true)
    ..writeAsStringSync('baseline');
  harness.code
    ..openWorkspace(root.path)
    ..recover()
    ..openFile(file.path);
  final open = harness.code.openFiles.single;
  harness.code.snapshot((open..controller.text = 'dirty text').path);
}

void main() {
  test('destination factory forwards typed start-task handoffs to Chat', () {
    final dir = Directory.systemTemp.createTempSync('start-task-factory-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final shell = ShellHarness(dir);
    const handoff = StartTaskHandoff('Check the run notes.');

    final inputs = DestinationInputs(
      client: shell.client,
      journey: shell.controller,
      code: shell.code,
      codeGuard: UnsavedWorkGuard(
        session: shell.code,
        prompt: (_) async => CloseChoice.cancel,
      ),
      alive: false,
      settings: shell.settings,
      pendingArgument: handoff,
      onProbe: () {},
      onInstall: (_) async => const {},
    );

    expect(
      (buildDestinationView(DestinationId.chat, inputs) as AgentView)
          .startTaskHandoff,
      handoff,
    );
  });

  testWidgets('denied guarded handoff does not preload later plain Chat',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('start-task-shell-');
    addTearDown(() => dir.deleteSync(recursive: true));
    var closeChoice = CloseChoice.cancel;
    final shell = ShellHarness(
      dir,
      closePrompt: (_) async => closeChoice,
    )..replyReady();

    await tester.pumpWidget(shell.app());
    await tester.pumpAndSettle();
    FlywheelNav.jump(
        tester.element(find.byType(JourneyView)), DestinationId.code);
    await tester.pumpAndSettle();
    expect(find.byType(CodeView), findsOneWidget);

    _prepareDirtyCode(shell);
    FlywheelNav.jump(
      tester.element(find.byType(CodeView)),
      DestinationId.chat,
      arg: const StartTaskHandoff('Blocked stale handoff'),
    );
    await tester.pumpAndSettle();
    expect(find.byType(CodeView), findsOneWidget);

    closeChoice = CloseChoice.discard;
    FlywheelNav.jump(tester.element(find.byType(CodeView)), DestinationId.chat);
    await tester.pumpAndSettle();

    expect(find.byType(AgentView), findsOneWidget);
    expect(find.text('Blocked stale handoff'), findsNothing);
  });

  testWidgets('start-task handoff preserves an existing dirty blank-chat draft',
      (tester) async {
    final h = _ChatHarness();
    addTearDown(h.dispose);

    await tester.pumpWidget(h.chat());
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const Key('start-task-input')), 'Existing unsent draft');
    await tester.pump();

    expect(h.draftTexts(), contains('Existing unsent draft'));

    await tester.pumpWidget(
        h.chat(handoff: const StartTaskHandoff('New journey handoff')));
    await tester.pumpAndSettle();

    expect(h.draftTexts(), [
      'Existing unsent draft',
      'New journey handoff',
    ]);
    expect(h.providerCalls, 0);
  });

  testWidgets('same handoff and cleared route do not duplicate drafts',
      (tester) async {
    final h = _ChatHarness();
    addTearDown(h.dispose);
    const handoff = StartTaskHandoff('Check the run notes.');

    await tester.pumpWidget(h.chat(handoff: handoff));
    await tester.pumpAndSettle();
    expect(h.draftTexts(), ['Check the run notes.']);

    await tester.pumpWidget(h.chat(handoff: handoff));
    await tester.pumpAndSettle();
    expect(h.draftTexts(), ['Check the run notes.']);

    await tester.pumpWidget(h.chat());
    await tester.pumpAndSettle();
    expect(h.draftTexts(), ['Check the run notes.']);

    await tester.pumpWidget(h.chat(handoff: handoff));
    await tester.pumpAndSettle();
    expect(h.draftTexts(), ['Check the run notes.']);
    expect(h.providerCalls, 0);
  });

  testWidgets('start-task handoff starts beside existing chat history',
      (tester) async {
    final h = _ChatHarness();
    addTearDown(h.dispose);
    h.history.save([
      Conversation(id: 'c42', messages: [
        ChatMessage(role: 'user', text: 'Earlier question'),
        ChatMessage(role: 'assistant', text: 'Earlier answer'),
      ])
    ]);

    await tester.pumpWidget(
        h.chat(handoff: const StartTaskHandoff('Follow up from Journey')));
    await tester.pumpAndSettle();

    final restored = h.history.load().single;
    expect(restored.messages.map((m) => m.text),
        ['Earlier question', 'Earlier answer']);
    expect(h.draftTexts(), ['Follow up from Journey']);
    expect(h.providerCalls, 0);
  });
}
