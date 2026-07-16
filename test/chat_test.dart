// The Chat surface: the conversation model derives a sidebar title and the
// gateway wire shape, and the thread renders user/assistant turns, fenced code,
// and the quiet 'verified' mark when a turn carried a receipt.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/models/gateway_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/compare_view.dart';
import 'package:flywheel_desktop/widgets/chat_thread.dart';
import 'package:flywheel_desktop/widgets/model_picker.dart';

Future<void> _pump(WidgetTester tester, Widget child) => tester.pumpWidget(
    MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: child)));

void main() {
  test('a conversation titles itself from the first user turn', () {
    final c = Conversation(id: 'c0');
    c.messages.add(ChatMessage(role: 'assistant', text: 'hi'));
    c.messages.add(ChatMessage(role: 'user', text: 'refactor the paginate() helper please'));
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

  testWidgets('the thread renders both turns and a fenced code block', (tester) async {
    final messages = [
      ChatMessage(role: 'user', text: 'show me a loop'),
      ChatMessage(
          role: 'assistant',
          text: 'Sure:\n```python\nfor i in range(3):\n    print(i)\n```\nDone.'),
    ];
    await _pump(tester, ChatThread(messages: messages, controller: ScrollController()));
    expect(find.textContaining('show me a loop'), findsOneWidget);
    expect(find.textContaining('Sure:'), findsWidgets);
    expect(find.textContaining('for i in range(3):'), findsOneWidget);   // the code card
  });

  testWidgets('an assistant turn with a receipt shows the quiet verified mark',
      (tester) async {
    final messages = [
      ChatMessage(
          role: 'assistant',
          text: 'answer',
          receipt: {'receipt_id': 'abc123'}),
    ];
    await _pump(tester, ChatThread(messages: messages, controller: ScrollController()));
    expect(find.text('verified'), findsOneWidget);
  });

  testWidgets('a streaming turn with no text yet shows a placeholder, not empty',
      (tester) async {
    final messages = [ChatMessage(role: 'assistant', text: '', streaming: true)];
    await _pump(tester, ChatThread(messages: messages, controller: ScrollController()));
    expect(find.text('…'), findsOneWidget);
  });

  EndpointRow _ep(String name, String cred) => EndpointRow(
      name: name, backend: 'b', credential: cred, providerRole: '', configured: true);

  testWidgets('the model picker button shows the current model', (tester) async {
    await _pump(
        tester,
        ModelPickerButton(
            endpoints: [_ep('local:14b', 'local-none'), _ep('claude', 'present')],
            current: 'claude',
            onSelect: (_) {}));
    expect(find.text('claude'), findsOneWidget);
  });

  testWidgets('opening the picker lets you search and select a model',
      (tester) async {
    String? chosen;
    await _pump(
        tester,
        ModelPickerButton(
            endpoints: [
              _ep('local:14b', 'local-none'),
              _ep('claude', 'present'),
              _ep('gemini', 'absent'),
            ],
            current: 'local:14b',
            onSelect: (v) => chosen = v));
    await tester.tap(find.byType(ModelPickerButton));
    await tester.pumpAndSettle();
    // credential state shows at a glance
    expect(find.text('ready'), findsWidgets); // claude has a key
    expect(find.text('no key'), findsOneWidget); // gemini has none
    await tester.enterText(find.byType(TextField), 'gem');
    await tester.pumpAndSettle();
    expect(find.text('claude'), findsNothing); // filtered out
    await tester.tap(find.text('gemini'));
    await tester.pumpAndSettle();
    expect(chosen, 'gemini');
  });

  testWidgets('Compare offline names the command that fixes it', (tester) async {
    await _pump(tester, CompareView(client: GatewayClient(), alive: false));
    expect(find.textContaining('flywheel up'), findsOneWidget);
  });
}
