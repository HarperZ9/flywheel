import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/chat_admission_controller.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:flywheel_desktop/views/compare_view.dart';
import 'package:flywheel_desktop/widgets/chat_thread.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Future<void> _pump(WidgetTester tester, Widget child) => tester.pumpWidget(
    MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: child)));

void main() {
  _historyTruthTests();
  test('complete envelope rejects excess bytes depth and nodes', () {
    final directory = _temporary('chat-draft-bounds-');
    final file = File('${directory.path}/drafts.json');
    final store = ChatDraftStore(file: file);
    dynamic deep = true;
    for (var i = 0; i < 18; i++) {
      deep = [deep];
    }
    for (final invalid in [
      'x' * 1048577,
      jsonEncode({'drafts': [], 'extra': deep, 'schema': 'invalid'}),
      jsonEncode(
          {'drafts': [], 'extra': List.filled(4097, 0), 'schema': 'invalid'}),
    ]) {
      file.writeAsStringSync(invalid);
      expect(() => store.load(), throwsA(isA<ChatDraftStoreException>()));
    }
  });
  _avatarTruthTests();
  _remoteRecoveryTests();
  _submittingRecoveryTests();
  test('a dragged split fraction is stored and read back, with a fallback', () {
    final s = DesktopSettings();
    expect(s.splitFraction('compare', 0.5), 0.5);
    s.setSplitFraction('compare', 0.62);
    expect(s.splitFraction('compare', 0.5), 0.62);
    expect(s.splitFraction('agent', 0.7), 0.7); // untouched views keep theirs
    s.cancelPendingSaves(); // the test never writes the real home dir
  });

  testWidgets('the agent chip swaps chat for the tool loop and back',
      (tester) async {
    await _pump(
        tester,
        AgentView(
            client: GatewayClient(), alive: true, settings: DesktopSettings()));
    await tester.pump();
    expect(find.text('Point the agent at a workspace'), findsNothing);
    expect(find.text('every reply is witnessed'), findsNothing);

    await tester.tap(find.text('agent'));
    await tester.pump();
    expect(find.text('Point the agent at a workspace'), findsOneWidget);
    expect(find.text('every run persists with its trace'), findsOneWidget);

    await tester.tap(find.text('chat'));
    await tester.pump();
    expect(find.text('Point the agent at a workspace'), findsNothing);
    expect(find.text('every reply is witnessed'), findsNothing);
  });

  testWidgets('compare panes sit on a draggable divider', (tester) async {
    await _pump(
        tester,
        CompareView(
            client: GatewayClient(), alive: true, settings: DesktopSettings()));
    await tester.pump();
    expect(find.byKey(const Key('split-divider')), findsOneWidget);
    expect(find.text('Pick a model and send a prompt.'), findsNWidgets(2));
  });
}

const _roster =
    '{"rows":[{"name":"local-public","backend":"local","credential":"local-none","provider_role":"","configured":true}]}';

String _frames(List<String> values) => [
      for (final value in values)
        'data: {"choices":[{"delta":{"content":"$value"}}]}\n\n',
      'data: [DONE]\n\n'
    ].join();

GatewayClient _client(String body, void Function() onChat) => GatewayClient(
    baseUrl: 'https://chat.invalid',
    httpClient: MockClient((request) async {
      if (request.url.path == '/api/endpoints') {
        return http.Response(_roster, 200);
      }
      onChat();
      return http.Response(body, 200);
    }));

Directory _temporary(String name) {
  final directory = Directory.systemTemp.createTempSync(name);
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}

Future<void> _pumpAgent(WidgetTester tester, GatewayClient client,
    ChatStore history, ChatDraftStore drafts) async {
  await _pump(
      tester,
      AgentView(
          client: client,
          alive: true,
          settings: DesktopSettings(),
          chatStore: history,
          draftStore: drafts));
  await tester.pumpAndSettle();
}

void _historyTruthTests() {
  test('legacy and envelope history cannot carry a verifier verdict', () {
    final directory = _temporary('chat-history-truth-');
    final file = File('${directory.path}/history.json');
    file.writeAsStringSync(jsonEncode([
      {
        'id': 'c0',
        'messages': [
          {
            'role': 'assistant',
            'text': 'legacy',
            'receipt': {'verified': true},
            'receipt_state': 'MATCH'
          }
        ]
      }
    ]));
    final store = ChatStore(file: file);
    expect(store.load().single.messages.single.receiptState,
        ReceiptState.presentUnchecked);
    final checked = Conversation(id: 'c1', messages: [
      ChatMessage(
          role: 'assistant',
          receipt: const {'receipt_id': 'r'},
          receiptState: ReceiptState.match)
    ]);
    expect(store.save([checked]), isTrue);
    expect(store.load().single.messages.single.receiptState,
        ReceiptState.presentUnchecked);
  });
}

void _avatarTruthTests() {
  testWidgets('assistant avatar is green only for typed MATCH', (tester) async {
    for (final state in const [
      ReceiptState.missing,
      ReceiptState.presentUnchecked,
      ReceiptState.unverifiable,
      ReceiptState.invalidResponse,
    ]) {
      await _pump(
          tester,
          ChatThread(messages: [
            ChatMessage(
                role: 'assistant',
                text: 'answer',
                receipt:
                    state == ReceiptState.missing ? null : const {'id': 'r'},
                receiptState:
                    state == ReceiptState.presentUnchecked ? null : state)
          ], controller: ScrollController()));
      expect(tester.widget<Text>(find.text('F')).style!.color,
          FwTokens.light.inkMuted);
    }
    await _pump(
        tester,
        ChatThread(messages: [
          ChatMessage(
              role: 'assistant',
              text: 'answer',
              receipt: const {'id': 'r'},
              receiptState: ReceiptState.match)
        ], controller: ScrollController()));
    expect(tester.widget<Text>(find.text('F')).style!.color,
        FwTokens.light.verified);
  });
}

void _remoteRecoveryTests() {
  testWidgets('history crash carries pair',
      (tester) => _exerciseRecovery(tester, 'one shot', 'first', 0, 1));
  testWidgets('cleanup retry stays local',
      (tester) => _exerciseRecovery(tester, 'cleanup prompt', 'answer', 5, 0));
  testWidgets(
      'failed tombstone is uncertain',
      (tester) =>
          _exerciseRecovery(tester, 'uncertain prompt', 'admitted', 3, 0));
  testWidgets('pending history is idempotent',
      (tester) => _exerciseRecovery(tester, 'one prompt', 'one answer', 4, 0));
}

Future<void> _exerciseRecovery(WidgetTester tester, String prompt,
    String answer, int draftFailure, int historyFailure) async {
  final directory = _temporary('chat-admission-recovery-');
  var draftWrites = 0;
  var historyWrites = 0;
  var chatCalls = 0;
  final drafts = ChatDraftStore(
      file: File('${directory.path}/drafts.json'),
      beforeRename: (_) {
        if (++draftWrites == draftFailure) throw StateError('injected');
      });
  final history = ChatStore(
      file: File('${directory.path}/history.json'),
      beforeRename: (_) {
        if (++historyWrites == historyFailure) throw StateError('injected');
      });
  final events = historyFailure == 1 ? [answer, 'second'] : [answer];
  await _pumpAgent(
      tester, _client(_frames(events), () => chatCalls++), history, drafts);
  await tester.enterText(find.byType(TextField), prompt);
  await tester.pump();
  await tester.tap(find.byTooltip('Send  (Enter)'));
  await tester.pumpAndSettle();
  expect(chatCalls, 1);
  final state = draftFailure == 5
      ? ChatDraftState.admittedPendingCleanup
      : draftFailure == 3
          ? ChatDraftState.submitting
          : ChatDraftState.admittedPendingHistory;
  final recover = draftFailure != 3;
  final hasHistory = draftFailure == 4 || draftFailure == 5;
  expect(drafts.load().single.state, state);
  expect(_texts(history), hasHistory ? [prompt, answer] : <String>[]);
  expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
      prompt);
  if (historyFailure == 1) expect(find.text('second'), findsNothing);
  if (!recover) {
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pumpAndSettle();
    expect(chatCalls, 1);
  }
  await tester.pumpWidget(const SizedBox());
  final resumedDrafts = ChatDraftStore(file: drafts.storageFile);
  final resumedHistory = ChatStore(file: history.storageFile);
  await _pumpAgent(tester, _client(_frames(['duplicate']), () => chatCalls++),
      resumedHistory, resumedDrafts);
  expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
      prompt);
  await tester.tap(find.byTooltip('Send  (Enter)'));
  await tester.pumpAndSettle();
  expect(chatCalls, 1);
  expect(_texts(resumedHistory), recover ? [prompt, answer] : <String>[]);
  if (recover) {
    expect(resumedDrafts.load(), isEmpty);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        isEmpty);
  } else {
    expect(resumedDrafts.load().single.state, ChatDraftState.submitting);
  }
}

List<String> _texts(ChatStore store) => [
      for (final conversation in store.load())
        for (final message in conversation.messages) message.text,
    ];

void _submittingRecoveryTests() {
  test('submitting plus complete history recovers without dispatch', () {
    final directory = _temporary('chat-submitting-history-');
    final drafts = ChatDraftStore(file: File('${directory.path}/drafts.json'))
      ..save(ChatDraft(
          draftRef: 'chd_${'a' * 32}',
          conversationRef: 'c0',
          text: 'already admitted',
          state: ChatDraftState.submitting,
          updatedAt: DateTime.parse('2026-08-15T12:00:00Z')));
    final history = ChatStore(file: File('${directory.path}/history.json'))
      ..save([
        Conversation(id: 'c0', messages: [
          ChatMessage(role: 'user', text: 'already admitted'),
          ChatMessage(role: 'assistant', text: 'durable answer'),
        ])
      ]);
    final controller = ChatAdmissionController(history, drafts)..restore();
    expect(drafts.load().single.state, ChatDraftState.admittedPendingCleanup);
    final disposition = controller.reconcileAdmitted(
        controller.conversations.single, 'already admitted');
    expect(disposition, PromptDisposition.accepted);
    expect(_texts(history), ['already admitted', 'durable answer']);
    expect(drafts.load(), isEmpty);
  });
}
