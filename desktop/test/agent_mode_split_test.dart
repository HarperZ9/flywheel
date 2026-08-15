// The Chat destination's agent mode and the shared resizable split: the
// header chips swap the chat surface for the gated tool loop, and compare's
// two panes sit on a real draggable divider whose fraction persists.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
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
  _avatarTruthTests();
  _oneShotAdmissionTests();
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
    // chat mode: the tool loop is absent and receipt truth stays neutral
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

Future<void> _pumpAgent(WidgetTester tester, AgentView view) async {
  await _pump(tester, view);
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

void _oneShotAdmissionTests() {
  testWidgets(
      'failed first-event history save closes admission to later frames',
      (tester) async {
    final directory = _temporary('chat-one-shot-history-');
    var historyWrites = 0;
    final history = ChatStore(
        file: File('${directory.path}/history.json'),
        beforeRename: (_) {
          if (++historyWrites == 1) throw StateError('injected');
        });
    final drafts = ChatDraftStore(file: File('${directory.path}/drafts.json'));
    var chatCalls = 0;
    await _pumpAgent(
        tester,
        AgentView(
            client: _client(_frames(['first', 'second']), () => chatCalls++),
            alive: true,
            settings: DesktopSettings(),
            chatStore: history,
            draftStore: drafts));
    await tester.enterText(find.byType(TextField), 'one shot');
    await tester.pump();
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pumpAndSettle();
    expect(chatCalls, 1);
    expect(history.load(), isEmpty);
    expect(drafts.load().single.state, ChatDraftState.retained);
    expect(find.text('second'), findsNothing);
  });

  testWidgets('visible admitted digest cannot transport after cleanup failure',
      (tester) async {
    final directory = _temporary('chat-one-shot-cleanup-');
    var draftWrites = 0;
    final drafts = ChatDraftStore(
        file: File('${directory.path}/drafts.json'),
        beforeRename: (_) {
          if (++draftWrites == 3) throw StateError('injected');
        });
    final history = ChatStore(file: File('${directory.path}/history.json'));
    var chatCalls = 0;
    await _pumpAgent(
        tester,
        AgentView(
            client: _client(_frames(['answer']), () => chatCalls++),
            alive: true,
            settings: DesktopSettings(),
            chatStore: history,
            draftStore: drafts));
    await tester.enterText(find.byType(TextField), 'one admitted prompt');
    await tester.pump();
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pumpAndSettle();
    expect(history.load().single.messages, hasLength(2));
    expect(drafts.load().single.state, ChatDraftState.submitting);
    await tester.tap(find.byTooltip('Stop'));
    await tester.pump();
    expect(find.byTooltip('Send  (Enter)'), findsOneWidget);
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pumpAndSettle();
    expect(chatCalls, 1);
    expect(history.load().single.messages, hasLength(2));
    expect(drafts.load().single.state, ChatDraftState.submitting);
  });
}
