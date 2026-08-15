import 'dart:async';
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
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _draftRef = 'chd_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
final _updated = DateTime.parse('2026-08-15T12:00:00Z');

Directory _temp(String name) {
  final result = Directory.systemTemp.createTempSync(name);
  addTearDown(() => result.deleteSync(recursive: true));
  return result;
}

ChatDraft _draft(String text) => ChatDraft(
    draftRef: _draftRef,
    conversationRef: 'c0',
    text: text,
    state: ChatDraftState.dirty,
    updatedAt: _updated);

void main() {
  _roundTripTests();
  _validationTests();
  _atomicFailureTests();
  _agentAdmissionTests();
}

void _roundTripTests() {
  test('canonical store keeps active and admitted custody independent', () {
    final directory = _temp('chat-draft-roundtrip-');
    final file = File('${directory.path}/drafts.json');
    final store = ChatDraftStore(file: file);
    _writeDrafts(file, const [
      ('a', 'c0', 'newer prompt', 'dirty'),
      ('b', 'c0', 'old prompt', 'admitted_pending_history'),
      ('c', 'c1', 'cleanup prompt', 'admitted_pending_cleanup'),
    ]);
    final loaded = store.load();
    expect(loaded.map((draft) => draft.state.name),
        ['dirty', 'admittedPendingHistory', 'admittedPendingCleanup']);
    store.save(loaded[1]);
    final controller = ChatAdmissionController(
        ChatStore(file: File('${directory.path}/history.json')), store,
        newAttemptRef: () => 'att_${'d' * 32}')
      ..restore();
    final conversation =
        controller.conversations.singleWhere((c) => c.id == 'c0');
    expect(controller.draftText(conversation), 'newer prompt');
    expect(controller.reconcileAdmitted(conversation, 'old prompt'),
        PromptDisposition.retained);
    expect(controller.prepare(conversation, 'newer prompt')!.attemptRef,
        'att_${'d' * 32}');
    expect(store.load().map((draft) => draft.state.name).toSet(),
        {'submitting', 'admittedPendingHistory', 'admittedPendingCleanup'});
    expect(() => loaded.add(_draft('later')), throwsUnsupportedError);
    expect(file.readAsStringSync(), startsWith('{"drafts":['));
    expect(file.readAsStringSync(),
        endsWith('"schema":"flywheel.desktop-chat-drafts/v1"}'));
  });
  test('digest delete requires the exact stored text digest', () {
    final directory = _temp('chat-draft-delete-');
    final store = ChatDraftStore(file: File('${directory.path}/drafts.json'));
    store.save(_draft('keep me'));
    expect(() => store.delete(_draftRef, expectedTextSha256: '0' * 64),
        throwsA(isA<ChatDraftStoreException>()));
    expect(store.load().single.text, 'keep me');
    store.delete(_draftRef, expectedTextSha256: store.load().single.textSha256);
    expect(store.load(), isEmpty);
  });
}

void _writeDrafts(File file, List<(String, String, String, String)> rows) {
  file.writeAsStringSync(jsonEncode({
    'drafts': [
      for (final row in rows)
        {
          if (row.$4[0] == 'a') 'assistant': {'role': 'assistant', 'text': 'a'},
          'conversation_ref': row.$2,
          'draft_ref': 'chd_${row.$1 * 32}',
          'state': row.$4,
          'text': row.$3,
          'text_sha256': _draft(row.$3).textSha256,
          'updated_at': _updated.toIso8601String(),
        }
    ],
    'schema': 'flywheel.desktop-chat-drafts/v1'
  }));
}

void _validationTests() {
  test('raw and decoded path or secret text fails without echo or write', () {
    final directory = _temp('chat-draft-private-');
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
        ChatDraftStore(file: file).save(_draft(unsafe));
      } catch (error) {
        failure = error;
      }
      expect(failure, isA<ChatDraftStoreException>());
      expect(failure.toString().contains(unsafe), isFalse);
      expect(file.existsSync(), isFalse);
    }
  });
  test('duplicate unknown stale and noncanonical records fail closed', () {
    final directory = _temp('chat-draft-corrupt-');
    final file = File('${directory.path}/drafts.json');
    final store = ChatDraftStore(file: file);
    store.save(_draft('hello'));
    final canonical = file.readAsStringSync();
    final fixtures = <String>[
      '{"drafts":[],"drafts":[],"schema":"flywheel.desktop-chat-drafts/v1"}',
      canonical.replaceFirst(
          '"state":"dirty"', '"state":"dirty","unknown":true'),
      canonical.replaceFirst(
          '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824',
          '0' * 64),
      const JsonEncoder.withIndent('  ').convert(jsonDecode(canonical)),
    ];
    for (final fixture in fixtures) {
      file.writeAsStringSync(fixture);
      expect(() => store.load(), throwsA(isA<ChatDraftStoreException>()));
    }
  });
}

void _atomicFailureTests() {
  test('temp collision and pre-rename failures preserve prior bytes', () {
    final directory = _temp('chat-draft-atomic-');
    final file = File('${directory.path}/drafts.json');
    ChatDraftStore(file: file).save(_draft('prior'));
    final before = file.readAsBytesSync();
    final collision = File('${directory.path}/collision.tmp')
      ..writeAsStringSync('mine');
    final collisionStore =
        ChatDraftStore(file: file, temporaryFile: (_) => collision);
    expect(() => collisionStore.save(_draft('next')),
        throwsA(isA<ChatDraftStoreException>()));
    expect(collision.readAsStringSync(), 'mine');
    expect(file.readAsBytesSync(), before);
    File? owned;
    final beforeStore = ChatDraftStore(
        file: file,
        temporaryFile: (_) => owned = File('${directory.path}/owned.tmp'),
        beforeRename: (_) => throw StateError('injected'));
    expect(() => beforeStore.save(_draft('next')),
        throwsA(isA<ChatDraftStoreException>()));
    expect(owned!.existsSync(), isFalse);
    expect(file.readAsBytesSync(), before);
  });
  test('rename and readback failures restore prior bytes and clean temp', () {
    final directory = _temp('chat-draft-readback-');
    final file = File('${directory.path}/drafts.json');
    final normal = ChatDraftStore(file: file)..save(_draft('prior'));
    final before = file.readAsBytesSync();
    File? noOpTemp;
    final noOp = ChatDraftStore(
        file: file,
        temporaryFile: (_) => noOpTemp = File('${directory.path}/noop.tmp'),
        renameFile: (_, __) {});
    expect(() => noOp.save(_draft('next')),
        throwsA(isA<ChatDraftStoreException>()));
    expect(noOpTemp!.existsSync(), isFalse);
    expect(file.readAsBytesSync(), before);
    final corrupt = ChatDraftStore(
        file: file,
        renameFile: (temporary, path) {
          temporary.renameSync(path);
          File(path).writeAsStringSync('{}');
        });
    expect(() => corrupt.save(_draft('next')),
        throwsA(isA<ChatDraftStoreException>()));
    expect(file.readAsBytesSync(), before);
    expect(normal.load().single.text, 'prior');
  });
}

class _AgentHarness {
  _AgentHarness({this.delayed, this.empty = false})
      : directory = Directory.systemTemp.createTempSync('chat-agent-') {
    drafts = ChatDraftStore(file: File('${directory.path}/drafts.json'));
    history = ChatStore(file: File('${directory.path}/history.json'));
    client = GatewayClient(
        baseUrl: 'https://chat.invalid',
        httpClient: MockClient((request) async {
          if (request.url.path == '/api/endpoints') {
            return http.Response(_roster, 200);
          }
          chatCalls++;
          return delayed?.future ??
              http.Response(empty ? 'data: [DONE]\n\n' : _reply, 200);
        }));
    addTearDown(dispose);
  }
  static const _roster =
      '{"rows":[{"name":"local-public","backend":"local","credential":"local-none","provider_role":"","configured":true}]}';
  static const _reply =
      'data: {"choices":[{"delta":{"content":"answer"}}]}\n\ndata: [DONE]\n\n';
  final Directory directory;
  final Completer<http.Response>? delayed;
  final bool empty;
  late final ChatDraftStore drafts;
  late final ChatStore history;
  late final GatewayClient client;
  var chatCalls = 0;
  AgentView view({ChatStore? historyStore}) => AgentView(
      client: client,
      alive: true,
      settings: DesktopSettings(),
      chatStore: historyStore ?? history,
      draftStore: drafts);
  void dispose() => directory.deleteSync(recursive: true);
}

Future<void> _pumpAgent(WidgetTester tester, AgentView view) async {
  await tester.pumpWidget(
      MaterialApp(theme: flywheelLightTheme(), home: Scaffold(body: view)));
  await tester.pumpAndSettle();
}

void _agentAdmissionTests() {
  testWidgets('accepted turn saves before clear and a newer edit survives',
      (tester) async {
    final reply = Completer<http.Response>();
    final harness = _AgentHarness(delayed: reply);
    await _pumpAgent(tester, harness.view());
    await tester.enterText(find.byType(TextField), 'old prompt');
    await tester.pump();
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pump();
    expect(harness.drafts.load().single.state, ChatDraftState.submitting);
    await tester.enterText(find.byType(TextField), 'newer prompt');
    reply.complete(http.Response(_AgentHarness._reply, 200));
    await tester.pumpAndSettle();
    expect(harness.chatCalls, 1);
    expect(harness.history.load().single.messages.map((m) => m.text),
        ['old prompt', 'answer']);
    expect(harness.drafts.load().single.text, 'newer prompt');
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        'newer prompt');
  });

  testWidgets('empty response retains draft and restart never auto-submits',
      (tester) async {
    final harness = _AgentHarness(empty: true);
    await _pumpAgent(tester, harness.view());
    await tester.enterText(find.byType(TextField), 'recover me');
    await tester.pump();
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pumpAndSettle();
    expect(harness.history.load(), isEmpty);
    expect(harness.drafts.load().single.text, 'recover me');
    await tester.pumpWidget(const SizedBox());
    await _pumpAgent(tester, harness.view());
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text,
        'recover me');
    expect(harness.chatCalls, 1);
  });

  testWidgets('dispose during admission leaves recoverable custody',
      (tester) async {
    final reply = Completer<http.Response>();
    final harness = _AgentHarness(delayed: reply);
    await _pumpAgent(tester, harness.view());
    await tester.enterText(find.byType(TextField), 'stay safe');
    await tester.pump();
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pump();
    await tester.pumpWidget(const SizedBox());
    reply.complete(http.Response(_AgentHarness._reply, 200));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(harness.history.load(), isEmpty);
    expect(harness.drafts.load().single.text, 'stay safe');
  });
}
