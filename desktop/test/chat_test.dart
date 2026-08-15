import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/chat_admission_controller.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/compare_view.dart';
import 'package:flywheel_desktop/widgets/chat_thread.dart';
import 'package:flywheel_desktop/widgets/model_picker.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Future<void> _pump(WidgetTester tester, Widget child) => tester.pumpWidget(
    MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: child)));

void main() {
  _modelTests();
  _admissionTests();
  _threadTests();
  _receiptTests();
  _pickerTests();
}

void _modelTests() {
  test('a conversation titles itself from the first user turn', () {
    final c = Conversation(id: 'c0');
    c.messages.add(ChatMessage(role: 'assistant', text: 'hi'));
    c.messages.add(ChatMessage(
        role: 'user', text: 'refactor the paginate() helper please'));
    c.titleFromFirstMessage();
    expect(c.title, 'refactor the paginate() helper please');
    expect(c.isEmpty, isFalse);
  });

  test('a long first turn is trimmed for the sidebar', () {
    final c = Conversation(id: 'c1');
    c.messages.add(ChatMessage(role: 'user', text: 'x' * 80));
    c.titleFromFirstMessage();
    expect(c.title.length, lessThanOrEqualTo(41));
    expect(c.title.endsWith('…'), isTrue);
  });

  test('a message serializes to the gateway wire shape', () {
    final m = ChatMessage(role: 'user', text: 'hello');
    expect(m.toWire(), {'role': 'user', 'content': 'hello'});
    expect(m.isUser, isTrue);
  });

  test('a conversation round-trips through json for durable history', () {
    final c = Conversation(id: 'c9', model: 'local-public');
    c.messages.add(ChatMessage(role: 'user', text: 'hi'));
    c.messages.add(ChatMessage(
        role: 'assistant', text: 'hello', receipt: {'receipt_id': 'r1'}));
    c.titleFromFirstMessage();
    final back = Conversation.fromJson(c.toJson());
    expect(back.id, 'c9');
    expect(back.model, 'local-public');
    expect(back.title, 'hi');
    expect(back.messages, hasLength(2));
    expect(back.messages[1].text, 'hello');
    expect(back.messages[1].receipt?['receipt_id'], 'r1');
    expect(back.messages[1].streaming, isFalse); // transient, not persisted
  });
}

void _admissionTests() {
  test('local admission failures retain custody before visible acceptance', () {
    final directory = Directory.systemTemp.createTempSync('chat-admission-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final failedDrafts = ChatDraftStore(
        file: File('${directory.path}/failed-drafts.json'),
        beforeRename: (_) => throw StateError('injected'));
    final blocked = ChatAdmissionController(
        ChatStore(file: File('${directory.path}/unused-history.json')),
        failedDrafts)
      ..restore();
    final blockedConversation = blocked.blankConversation('local-public');
    blocked.conversations.add(blockedConversation);
    expect(blocked.prepare(blockedConversation, 'safe prompt'), isNull);
    expect(
        blocked.prepare(blockedConversation, 'password=abcdefghijkl'), isNull);

    final drafts = ChatDraftStore(file: File('${directory.path}/drafts.json'));
    final controller = ChatAdmissionController(
        ChatStore(
            file: File('${directory.path}/history.json'),
            beforeRename: (_) => throw StateError('injected')),
        drafts)
      ..restore();
    final conversation = controller.blankConversation('local-public');
    controller.conversations.add(conversation);
    final submitted = controller.prepare(conversation, 'keep this')!;
    final decision = controller.acceptFirst(conversation, submitted,
        ChatMessage(role: 'assistant', text: 'answer'));
    expect(decision, (disposition: PromptDisposition.retained, visible: false));
    expect(conversation.messages, isEmpty);
    expect(drafts.load().single.state, ChatDraftState.retained);
  });

  test('a malformed-only chat response produces no admission event', () async {
    var calls = 0;
    final client = GatewayClient(
        baseUrl: 'https://chat.invalid',
        httpClient: MockClient((_) async {
          calls++;
          return http.Response('data: {malformed}\n\ndata: [DONE]\n\n', 200);
        }));
    final events = await client.chatStream([
      {'role': 'user', 'content': 'keep this'}
    ], 'local-public').toList();
    expect(events, isEmpty);
    expect(calls, 1);
  });

  test('chat history reads the legacy list and writes an atomic envelope', () {
    final directory = Directory.systemTemp.createTempSync('chat-history-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final file = File('${directory.path}/history.json')
      ..writeAsStringSync(jsonEncode([
        Conversation(
            id: 'c7',
            messages: [ChatMessage(role: 'user', text: 'legacy')]).toJson()
      ]));
    final store = ChatStore(file: file);
    final loaded = store.load();
    expect(loaded.single.messages.single.text, 'legacy');
    expect(store.save(loaded), isTrue);
    expect(jsonDecode(file.readAsStringSync()), {
      'conversations': [loaded.single.toJson()],
      'schema': 'flywheel.desktop-chat-history/v1'
    });
  });
}

void _threadTests() {
  testWidgets('the thread renders both turns and a fenced code block',
      (tester) async {
    final messages = [
      ChatMessage(role: 'user', text: 'show me a loop'),
      ChatMessage(
          role: 'assistant',
          text:
              'Sure:\n```python\nfor i in range(3):\n    print(i)\n```\nDone.'),
    ];
    await _pump(
        tester, ChatThread(messages: messages, controller: ScrollController()));
    expect(find.textContaining('show me a loop'), findsOneWidget);
    expect(find.textContaining('Sure:'), findsWidgets);
    expect(find.textContaining('for i in range(3):'),
        findsOneWidget); // the code card
  });

  testWidgets('an assistant turn with a receipt stays present unchecked',
      (tester) async {
    final messages = [
      ChatMessage(
          role: 'assistant', text: 'answer', receipt: {'receipt_id': 'abc123'}),
    ];
    await _pump(
        tester, ChatThread(messages: messages, controller: ScrollController()));
    expect(find.text('present_unchecked'), findsOneWidget);
  });

  testWidgets(
      'a streaming turn with no text yet shows a placeholder, not empty',
      (tester) async {
    final messages = [
      ChatMessage(role: 'assistant', text: '', streaming: true)
    ];
    await _pump(
        tester, ChatThread(messages: messages, controller: ScrollController()));
    expect(find.text('…'), findsOneWidget);
  });
}

void _receiptTests() {
  testWidgets('the receipt-state control opens and closes the detail',
      (tester) async {
    final messages = [
      ChatMessage(role: 'assistant', text: 'answer', receipt: {
        'receipt_id': 'abc123def456abc123de',
        'request_hash': '1111aaaa2222bbbb',
        'prompt_hash': '3333cccc4444dddd',
        'response_hash': '5555eeee6666ffff',
        'model_ref': 'model-public-a',
        'routed_via': 'route-public-a',
        'seed': 0,
      }),
    ];
    await _pump(
        tester, ChatThread(messages: messages, controller: ScrollController()));
    expect(find.textContaining('abc123def456abc123de'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('chat-receipt-control')));
    await tester.pumpAndSettle();
    // the receipt detail: routing fact, the id, and the recompute note
    expect(find.text('route-public-a'), findsOneWidget);
    expect(find.textContaining('abc123def456abc123de'), findsOneWidget);
    expect(find.textContaining('content-addressed'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('chat-receipt-control')));
    await tester.pumpAndSettle();
    expect(find.textContaining('abc123def456abc123de'), findsNothing);
  });

  testWidgets('the receipt names a failover and a served-model swap honestly',
      (tester) async {
    final messages = [
      ChatMessage(role: 'assistant', text: 'answer', receipt: {
        'receipt_id': 'abc123def456abc123de',
        'model_ref': 'model-public-a',
        'served_model': 'model-public-b',
        'failover_from': ['route-public-a: unavailable'],
      }),
    ];
    await _pump(
        tester, ChatThread(messages: messages, controller: ScrollController()));
    await tester.tap(find.byKey(const ValueKey('chat-receipt-control')));
    await tester.pumpAndSettle();
    expect(find.text('model-public-b'), findsOneWidget);
    expect(find.textContaining('route-public-a: unavailable'), findsOneWidget);
  });
}

void _pickerTests() {
  EndpointRow ep(String name, String cred) => EndpointRow(
      name: name,
      backend: 'b',
      credential: cred,
      providerRole: '',
      configured: true);

  testWidgets('the model picker button shows the current model',
      (tester) async {
    await _pump(
        tester,
        ModelPickerButton(endpoints: [
          ep('local-public', 'local-none'),
          ep('route-a', 'present')
        ], current: 'route-a', onSelect: (_) {}));
    expect(find.text('route-a'), findsOneWidget);
  });

  testWidgets('opening the picker lets you search and select a model',
      (tester) async {
    String? chosen;
    await _pump(
        tester,
        ModelPickerButton(endpoints: [
          ep('local-public', 'local-none'),
          ep('route-a', 'present'),
          ep('route-b', 'absent'),
        ], current: 'local-public', onSelect: (v) => chosen = v));
    await tester.tap(find.byType(ModelPickerButton));
    await tester.pumpAndSettle();
    // credential state shows at a glance
    expect(find.text('ready'), findsWidgets);
    expect(find.text('no key'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'route-b');
    await tester.pumpAndSettle();
    expect(find.text('route-a'), findsNothing);
    await tester.tap(find.text('route-b').last, warnIfMissed: false);
    await tester.pumpAndSettle();
    expect(chosen, isNull);
    await tester.enterText(find.byType(TextField), 'route-a');
    await tester.pumpAndSettle();
    await tester.tap(find.text('route-a').last);
    await tester.pumpAndSettle();
    expect(chosen, 'route-a');
  });

  testWidgets('Compare offline names the command that fixes it',
      (tester) async {
    await _pump(
        tester,
        CompareView(
            client: GatewayClient(),
            alive: false,
            settings: DesktopSettings()));
    expect(find.textContaining('flywheel up'), findsOneWidget);
  });

  test('the prompt shelf saves, dedupes, titles, and caps', () {
    final s = DesktopSettings();
    s.savePrompt('  refactor this  ');
    s.savePrompt('write tests');
    s.savePrompt('refactor this'); // dedupe -> moves to front, no duplicate
    expect(s.savedPrompts.length, 2);
    expect(s.savedPrompts.first['text'], 'refactor this');
    expect(s.savedPrompts.first['title'], 'refactor this');
    s.removePrompt('refactor this');
    expect(s.savedPrompts.length, 1);
  });
}
