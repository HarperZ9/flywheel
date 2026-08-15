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
  _historyAndAvatarTruthTests();
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
  _remoteRecoveryTests();
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

void _historyAndAvatarTruthTests() {
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
  testWidgets('assistant avatar is green only for typed MATCH', (tester) async {
    for (final state in const [
      ReceiptState.missing,
      ReceiptState.presentUnchecked,
      ReceiptState.unverifiable,
      ReceiptState.invalidResponse,
    ]) {
      await _pump(tester, _avatarThread(state));
      expect(tester.widget<Text>(find.text('F')).style!.color,
          FwTokens.light.inkMuted);
    }
    await _pump(tester, _avatarThread(ReceiptState.match));
    expect(tester.widget<Text>(find.text('F')).style!.color,
        FwTokens.light.verified);
  });
}

ChatThread _avatarThread(ReceiptState state) => ChatThread(messages: [
      ChatMessage(
          role: 'assistant',
          text: 'answer',
          receipt: state == ReceiptState.missing ? null : const {'id': 'r'},
          receiptState: state == ReceiptState.presentUnchecked ? null : state)
    ], controller: ScrollController());
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
  test('identical older history cannot satisfy a newer or legacy attempt', () {
    final directory = _temporary('chat-submitting-history-');
    for (final current in [null, 'att_${'b' * 32}']) {
      final drafts = ChatDraftStore(
          file: File('${directory.path}/drafts-${current ?? 'legacy'}.json'))
        ..save(ChatDraft(
            draftRef: 'chd_${'b' * 32}',
            conversationRef: 'c0',
            text: 'same prompt',
            state: ChatDraftState.submitting,
            updatedAt: DateTime.parse('2026-08-15T12:00:00Z'),
            attemptRef: current));
      final old = current == null ? null : 'att_${'a' * 32}';
      final history = ChatStore(
          file: File('${directory.path}/history-${current ?? 'legacy'}.json'))
        ..save([
          Conversation(id: 'c0', messages: [
            ChatMessage(role: 'user', text: 'same prompt', attemptRef: old),
            ChatMessage(
                role: 'assistant', text: 'same answer', attemptRef: old),
          ])
        ]);
      final controller = ChatAdmissionController(history, drafts)..restore();
      final conversation = controller.conversations.single;
      expect(drafts.load().single.state, ChatDraftState.submitting);
      expect(controller.reconcileAdmitted(conversation, 'same prompt'),
          PromptDisposition.retained);
      expect(controller.prepare(conversation, 'same prompt'), isNull);
      expect(drafts.load().single.attemptRef, current);
      expect(_texts(history), ['same prompt', 'same answer']);
    }
  });
}

Future<void> _exerciseRecovery(WidgetTester tester, String prompt,
    String answer, int draftFailure, int historyFailure) async {
  final directory = _temporary('chat-admission-recovery-');
  var draftWrites = 0;
  var historyWrites = 0;
  var chatCalls = 0;
  final collision = historyFailure == 1;
  final historyFile = File('${directory.path}/history.json');
  final oldAttempt = 'att_${'a' * 32}';
  if (collision) {
    ChatStore(file: historyFile).save([
      Conversation(id: 'c0', messages: [
        ChatMessage(role: 'user', text: prompt, attemptRef: oldAttempt),
        ChatMessage(role: 'assistant', text: answer, attemptRef: oldAttempt),
      ])
    ]);
  }
  final drafts = ChatDraftStore(
      file: File('${directory.path}/drafts.json'),
      beforeRename: (_) {
        if (++draftWrites == draftFailure) throw StateError('injected');
      });
  final history = ChatStore(
      file: historyFile,
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
  final hasHistory = draftFailure == 4 || draftFailure == 5 || collision;
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
  final expected = recover ? [prompt, answer] : <String>[];
  if (collision) expected.addAll([prompt, answer]);
  expect(_texts(resumedHistory), expected);
  if (collision) {
    final messages = resumedHistory.load().single.messages;
    final refs = [for (final message in messages) message.attemptRef];
    expect(refs.sublist(0, 2), [oldAttempt, oldAttempt]);
    expect((refs.length, refs[2] == refs[3], refs[2] != oldAttempt),
        (4, true, true));
  }
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
