import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/models/evidence_state.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:flywheel_desktop/widgets/chat_composer.dart';
import 'package:flywheel_desktop/widgets/chat_header.dart';
import 'package:flywheel_desktop/widgets/chat_thread.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Future<void> _pump(WidgetTester tester, Widget child) => tester.pumpWidget(
    MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: child)));
void main() {
  _receiptModelTests();
  _receiptLabelWidgetTests();
  _receiptControlWidgetTests();
  _composerTests();
  _admissionTests();
}

void _receiptModelTests() {
  test('receipt presence stays unchecked and caller maps cannot mutate it', () {
    final nested = <String, dynamic>{'value': 'original'};
    final raw = <String, dynamic>{'verified': true, 'nested': nested};
    final message = ChatMessage(role: 'assistant', receipt: raw);
    nested['value'] = 'changed';
    raw['later'] = true;
    expect(message.receiptState, ReceiptState.presentUnchecked);
    expect((message.receipt!['nested'] as Map)['value'], 'original');
    expect(message.receipt!.containsKey('later'), isFalse);
    expect(() => message.receipt!['added'] = true, throwsUnsupportedError);
  });
  test('only allowed independent receipt states survive normalization', () {
    for (final state in const [
      ReceiptState.match,
      ReceiptState.drift,
      ReceiptState.tampered,
      ReceiptState.unverifiable,
    ]) {
      final actual = ChatMessage(
          role: 'assistant', receipt: const {'id': 'r'}, receiptState: state);
      expect(actual.receiptState, state);
    }
    expect(ChatMessage(role: 'assistant').receiptState, ReceiptState.missing);
    final absent =
        ChatMessage(role: 'assistant', receiptState: ReceiptState.match);
    final contradiction = ChatMessage(
        role: 'assistant',
        receipt: const {'id': 'r'},
        receiptState: ReceiptState.missing);
    expect((absent.receiptState, contradiction.receiptState),
        (ReceiptState.invalidResponse, ReceiptState.invalidResponse));
  });
  test('history reload degrades MATCH and ignores carried verifier state', () {
    final checked = ChatMessage(
        role: 'assistant',
        receipt: const {'receipt_id': 'r'},
        receiptState: ReceiptState.match);
    final reloaded = ChatMessage.fromJson(checked.toJson());
    expect(reloaded.receiptState, ReceiptState.presentUnchecked);
    expect(checked.toJson().containsKey('receipt_state'), isFalse);
    final unknown = ChatMessage.fromJson({
      'role': 'assistant',
      'text': 'answer',
      'receipt': {'receipt_id': 'r'},
      'receipt_state': 'UNKNOWN',
    });
    expect(unknown.receiptState, ReceiptState.presentUnchecked);
    final malformed =
        ChatMessage.fromJson({'role': 'assistant', 'receipt': 'not-a-receipt'});
    expect(malformed.receiptState, ReceiptState.invalidResponse);
  });
}

void _receiptLabelWidgetTests() {
  testWidgets('missing and unchecked never promote', (tester) async {
    await _pump(
        tester,
        ChatThread(messages: [
          ChatMessage(role: 'assistant', text: 'without'),
          ChatMessage(
              role: 'assistant',
              text: 'with',
              receipt: {'verified': true, 'hash': 'a' * 64}),
        ], controller: ScrollController()));
    expect(find.text('missing'), findsOneWidget);
    expect(find.text('present_unchecked'), findsOneWidget);
    expect(find.text('verified'), findsNothing);
    expect(find.text('MATCH'), findsNothing);
    expect(find.byKey(const ValueKey('chat-receipt-control')), findsOneWidget);
  });
  testWidgets('only an independent MATCH renders MATCH', (tester) async {
    await _pump(
        tester,
        ChatThread(messages: [
          ChatMessage(
              role: 'assistant',
              text: 'checked',
              receipt: const {'receipt_id': 'r'},
              receiptState: ReceiptState.match),
        ], controller: ScrollController()));
    expect(find.text('MATCH'), findsOneWidget);
    expect(find.text('verified'), findsNothing);
  });
}

void _receiptControlWidgetTests() {
  testWidgets('receipt detail supports pointer and keyboard', (tester) async {
    final semantics = tester.ensureSemantics();
    await _pump(
        tester,
        ChatThread(messages: [
          ChatMessage(role: 'assistant', text: 'answer', receipt: const {
            'receipt_id': 'receipt_public_1',
            'model_ref': 'model_public_1',
            'routed_via': 'route_public_1',
          }),
        ], controller: ScrollController()));
    final control = find.byKey(const ValueKey('chat-receipt-control'));
    expect(
        tester.getSemantics(control),
        matchesSemantics(
            label: 'Receipt state present_unchecked',
            isButton: true,
            hasEnabledState: true,
            isEnabled: true,
            hasExpandedState: true,
            isExpanded: false,
            hasTapAction: true));
    await tester.tap(control);
    await tester.pumpAndSettle();
    expect(find.textContaining('receipt_public_1'), findsOneWidget);
    final button = tester.widget<TextButton>(control);
    button.focusNode!.requestFocus();
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.textContaining('receipt_public_1'), findsNothing);
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pumpAndSettle();
    expect(find.textContaining('receipt_public_1'), findsOneWidget);
    semantics.dispose();
  });
  testWidgets('header makes a neutral receipt-state promise', (tester) async {
    await _pump(
        tester,
        ChatHeader(
            agentMode: false,
            streaming: false,
            endpoints: const [],
            endpoint: null,
            chosenModel: null,
            onMode: (_) {},
            onEndpoint: (_) {},
            onModel: (_) {},
            loadModels: () async => const {}));
    expect(find.text('receipt state shown on every reply'), findsOneWidget);
    expect(find.text('every reply is witnessed'), findsNothing);
    expect(find.byIcon(Icons.verified_outlined), findsNothing);
  });
}

void _composerTests() {
  testWidgets('retained stays and accepted clears unchanged text',
      (tester) async {
    var disposition = PromptDisposition.retained;
    String? submitted;
    await _pump(
        tester,
        ChatComposer(
            streaming: false,
            initialText: '  exact prompt  ',
            onDraftChanged: (_) {},
            onSend: (text) async {
              submitted = text;
              return disposition;
            }));
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pump();
    expect(submitted, '  exact prompt  ');
    expect(_editorText(tester), '  exact prompt  ');
    disposition = PromptDisposition.accepted;
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pump();
    expect(_editorText(tester), isEmpty);
  });
  testWidgets('one pending submit cannot clear a newer edit', (tester) async {
    final result = Completer<PromptDisposition>();
    var calls = 0;
    await _pump(
        tester,
        ChatComposer(
            streaming: false,
            initialText: 'old prompt',
            onDraftChanged: (_) {},
            onSend: (_) {
              calls++;
              return result.future;
            }));
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.enterText(find.byType(TextField), 'newer prompt');
    result.complete(PromptDisposition.accepted);
    await tester.pump();
    expect(calls, 1);
    expect(_editorText(tester), 'newer prompt');
  });
}

void _admissionTests() {
  test('raw and decoded path or secret text fails without echo or write', () {
    final directory = Directory.systemTemp.createTempSync('chat-private-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final file = File('${directory.path}/drafts.json');
    for (final unsafe in const [
      r'open C:\private\note.txt',
      r'open %43%3A%5Cprivate%5Cnote.txt',
      r'open \\host\share\note.txt',
      'read /etc/passwd',
      'open file:///private/note.txt',
      'password=abcdefghijkl',
      'api%5Fkey%3Dabcdefghijkl',
      'ordinary %word then %2Fetc%2Fpasswd',
      '-----BEGIN PRIVATE KEY-----',
    ]) {
      Object? failure;
      try {
        ChatDraftStore(file: file).save(_localDraft(unsafe));
      } catch (error) {
        failure = error;
      }
      expect(failure, isA<ChatDraftStoreException>());
      expect(failure.toString(), isNot(contains(unsafe)));
      expect(file.existsSync(), isFalse);
    }
  });
  test('unicode and ordinary literal percent draft text remain admissible', () {
    final directory = Directory.systemTemp.createTempSync('chat-unicode-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final store = ChatDraftStore(file: File('${directory.path}/drafts.json'));
    store.save(_localDraft("Résumé 50% complete %word trailing% SQL '%foo%' "
        '日本語 %E2%9C%93'));
    expect(store.load().single.text,
        "Résumé 50% complete %word trailing% SQL '%foo%' 日本語 %E2%9C%93");
  });
  testWidgets('no model retains draft with zero chat calls', (tester) async {
    final directory = Directory.systemTemp.createTempSync('chat-no-model-');
    addTearDown(() => directory.deleteSync(recursive: true));
    var chatCalls = 0;
    final transport = MockClient((request) async {
      if (request.url.path == '/api/endpoints') {
        return http.Response(jsonEncode({'rows': []}), 200);
      }
      chatCalls++;
      return http.Response('', 500);
    });
    final drafts = ChatDraftStore(file: File('${directory.path}/drafts.json'));
    await _pump(
        tester,
        AgentView(
            client: GatewayClient(
                baseUrl: 'https://chat.invalid', httpClient: transport),
            alive: true,
            settings: DesktopSettings(),
            chatStore: ChatStore(file: File('${directory.path}/history.json')),
            draftStore: drafts));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '  exact safe prompt  ');
    await tester.pump();
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pump();
    expect(chatCalls, 0);
    expect(_editorText(tester), '  exact safe prompt  ');
    expect(drafts.load().single.text, '  exact safe prompt  ');
  });
}

ChatDraft _localDraft(String text) => ChatDraft(
    draftRef: 'chd_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    conversationRef: 'c0',
    text: text,
    state: ChatDraftState.dirty,
    updatedAt: DateTime.parse('2026-08-15T12:00:00Z'));

String _editorText(WidgetTester tester) =>
    tester.widget<TextField>(find.byType(TextField)).controller!.text;
