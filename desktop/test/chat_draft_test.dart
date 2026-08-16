import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/chat_admission_controller.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _ref = 'chd_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _done = ChatDraftState.admittedPendingCleanup,
    _dirty = ChatDraftState.dirty;
const _history = ChatDraftState.admittedPendingHistory;
const _submitting = ChatDraftState.submitting;
typedef _Reply = Completer<http.Response>;
final _updated = DateTime.parse('2026-08-15T12:00:00Z');
Directory _temp(String name) {
  final result = Directory.systemTemp.createTempSync(name);
  addTearDown(() => result.deleteSync(recursive: true));
  return result;
}

ChatDraft _draft(String text) => ChatDraft(
    draftRef: _ref,
    conversationRef: 'c0',
    text: text,
    state: _dirty,
    updatedAt: _updated);
ChatDraft _attempt(String key, String text, ChatDraftState s, [String? a]) =>
    ChatDraft(
        draftRef: 'chd_${key * 32}',
        conversationRef: 'c0',
        text: text,
        state: s,
        updatedAt: _updated,
        attemptRef: 'att_${(a ?? key) * 32}',
        assistantEvent: s.index < 3 ? null : _assistant(a ?? key));
Map<String, dynamic> _assistant(String key) =>
    {'attempt_ref': 'att_${key * 32}', 'role': 'assistant', 'text': 'answer'};
void main() {
  _atomicFailureTests();
  _agentAdmissionTests();
  test('canonical store keeps active and admitted custody independent', () {
    final file = File('${_temp('chat-draft-roundtrip-').path}/drafts.json');
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
        ChatStore(file: File('${file.parent.path}/history.json')), store,
        newAttemptRef: () => 'att_${'d' * 32}')
      ..restore();
    final c = controller.conversations.singleWhere((c) => c.id == 'c0');
    expect(controller.draftText(c), 'newer prompt');
    expect(controller.reconcileAdmitted(c, 'old prompt'),
        PromptDisposition.retained);
    expect(
        controller.prepare(c, 'newer prompt')!.attemptRef, 'att_${'d' * 32}');
    expect(_states(store), {_dirty, _submitting, _history, _done});
    expect(() => loaded.add(_draft('later')), throwsUnsupportedError);
    expect(file.readAsStringSync(), startsWith('{"drafts":['));
    expect(file.readAsStringSync(),
        endsWith('"schema":"flywheel.desktop-chat-drafts/v1"}'));
  });
  test('digest delete requires the exact stored text digest', () {
    final store = ChatDraftStore(
        file: File('${_temp('chat-draft-delete-').path}/drafts.json'));
    store.save(_draft('keep me'));
    _fails(() => store.delete(_ref, expectedTextSha256: '0' * 64));
    expect(store.load().single.text, 'keep me');
    store.delete(_ref, expectedTextSha256: store.load().single.textSha256);
    expect(store.load(), isEmpty);
  });
  test('active draft and exact attempt custodies coexist independently', () {
    final file = File('${_temp('chat-draft-custody-').path}/drafts.json');
    final store = ChatDraftStore(file: file);
    final first = _attempt('b', 'old prompt', _submitting);
    final second = _attempt('c', 'other prompt', _submitting);
    store
      ..save(_draft('newer draft'))
      ..save(first)
      ..save(second);
    expect(_texts(store), {'newer draft', 'old prompt', 'other prompt'});
    store.save(_attempt('b', 'old prompt', _history));
    expect(_states(store), {_dirty, _submitting, _history});
    final admitted =
        store.load().singleWhere((draft) => draft.state == _history);
    _fails(() => store.save(_attempt('c', 'collision', _submitting, 'e')));
    _fails(() => store.delete(second.draftRef, expectedTextSha256: '0' * 64));
    final canonical = file.readAsStringSync();
    file.writeAsStringSync(
        canonical.replaceFirst('att_${'c' * 32}', 'att_${'b' * 32}'));
    _fails(store.load);
    file.writeAsStringSync(canonical);
    store.delete(admitted.draftRef, expectedTextSha256: admitted.textSha256);
    expect(_texts(store), {'newer draft', 'other prompt'});
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
    _fails(() => collisionStore.save(_draft('next')));
    expect(collision.readAsStringSync(), 'mine');
    expect(file.readAsBytesSync(), before);
    File? owned;
    final beforeStore = ChatDraftStore(
        file: file,
        temporaryFile: (_) => owned = File('${directory.path}/owned.tmp'),
        beforeRename: (_) => throw StateError('injected'));
    _fails(() => beforeStore.save(_draft('next')));
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
    _fails(() => noOp.save(_draft('next')));
    expect(noOpTemp!.existsSync(), isFalse);
    expect(file.readAsBytesSync(), before);
    final corrupt = ChatDraftStore(
        file: file,
        renameFile: (temporary, path) {
          temporary.renameSync(path);
          File(path).writeAsStringSync('{}');
        });
    _fails(() => corrupt.save(_draft('next')));
    expect(file.readAsBytesSync(), before);
    expect(normal.load().single.text, 'prior');
  });
}

_fails(f) => expect(f, throwsA(isA<ChatDraftStoreException>()));
Set<String> _texts(ChatDraftStore s) => s.load().map((d) => d.text).toSet();
_states(ChatDraftStore s) => s.load().map((d) => d.state).toSet();

class _AgentHarness {
  _AgentHarness({_Reply? delayed, bool empty = false, int? failWrite}) {
    final directory = _temp('chat-agent-');
    drafts = ChatDraftStore(
        file: File('${directory.path}/drafts.json'),
        beforeRename: (_) {
          if (++draftWrites == failWrite) throw StateError('injected');
        });
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
  }
  static const _roster =
      '{"rows":[{"name":"local-public","backend":"local","credential":"local-none","provider_role":"","configured":true}]}';
  static const _reply =
      'data: {"choices":[{"delta":{"content":"answer"}}]}\n\ndata: [DONE]\n\n';
  late final ChatDraftStore drafts;
  late final ChatStore history;
  late final GatewayClient client;
  var chatCalls = 0, draftWrites = 0;
  AgentView view({ChatDraftStore? draftStore}) => AgentView(
      client: client,
      alive: true,
      settings: DesktopSettings(),
      chatStore: history,
      draftStore: draftStore ?? drafts);
}

Future<void> _pumpAgent(WidgetTester tester, AgentView view) async {
  await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(), home: Scaffold(body: _granted(view))));
  await tester.pumpAndSettle();
}

Widget _granted(Widget child) => GatewayOperationScope(
    authorize: (_, operation, dispatch) => dispatch(
        operation.finalBody('jrn_${'a' * 32}', 'a' * 64, 'gnt_${'a' * 32}')),
    child: child);

Future<(_AgentHarness, _Reply)> _pending(WidgetTester tester, String text,
    [int? failWrite]) async {
  final reply = _Reply();
  final harness = _AgentHarness(delayed: reply, failWrite: failWrite);
  await _pumpAgent(tester, harness.view());
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.byTooltip('Send  (Enter)'));
  await tester.pump();
  return (harness, reply);
}

void _agentAdmissionTests() {
  testWidgets('new edit keeps an ambiguous attempt', (tester) async {
    final (agent, reply) = await _pending(tester, 'old prompt', 4);
    await tester.enterText(find.byType(TextField), 'newer draft');
    reply.complete(http.Response(_AgentHarness._reply, 200));
    await tester.pumpAndSettle();
    expect(agent.chatCalls, 1);
    expect(agent.history.load(), isEmpty);
    expect(_texts(agent.drafts), {'old prompt', 'newer draft'});
    await tester.pumpWidget(const SizedBox());
    final fresh = ChatDraftStore(file: agent.drafts.storageFile);
    await _pumpAgent(tester, agent.view(draftStore: fresh));
    expect(_editorText(tester), 'newer draft');
    await tester.enterText(find.byType(TextField), 'old prompt');
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pumpAndSettle();
    expect(agent.chatCalls, 1);
    expect(agent.history.load(), isEmpty);
    expect(_texts(fresh), {'old prompt', 'newer draft'});
  });
  testWidgets('accepted turn saves and preserves a newer edit', (tester) async {
    final (agent, reply) = await _pending(tester, 'old prompt');
    expect(_states(agent.drafts), {_dirty, _submitting});
    await tester.enterText(find.byType(TextField), 'newer prompt');
    reply.complete(http.Response(_AgentHarness._reply, 200));
    await tester.pumpAndSettle();
    expect(agent.chatCalls, 1);
    expect(agent.history.load().single.messages.map((m) => m.text),
        ['old prompt', 'answer']);
    expect(agent.drafts.load().single.text, 'newer prompt');
    expect(_editorText(tester), 'newer prompt');
  });
  testWidgets('empty response never autosubmits on restart', (tester) async {
    final agent = _AgentHarness(empty: true);
    await _pumpAgent(tester, agent.view());
    await tester.enterText(find.byType(TextField), 'recover me');
    await tester.pump();
    await tester.tap(find.byTooltip('Send  (Enter)'));
    await tester.pumpAndSettle();
    expect(agent.history.load(), isEmpty);
    expect(_states(agent.drafts), {_dirty, _submitting});
    expect(_texts(agent.drafts), {'recover me'});
    await tester.pumpWidget(const SizedBox());
    await _pumpAgent(tester, agent.view());
    expect(_editorText(tester), 'recover me');
    expect(agent.chatCalls, 1);
  });
  testWidgets('dispose leaves recoverable admission custody', (tester) async {
    final (agent, reply) = await _pending(tester, 'stay safe');
    await tester.pumpWidget(const SizedBox());
    reply.complete(http.Response(_AgentHarness._reply, 200));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(agent.history.load(), isEmpty);
    expect(_states(agent.drafts), {_dirty, _submitting});
  });
}

_editorText(t) => t.widget<TextField>(find.byType(TextField)).controller!.text;
