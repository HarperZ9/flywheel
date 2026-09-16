import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

part 'chat_context_lifecycle_harness.dart';

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _b = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
const _c = 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc';
const _binding = GatewayJourneyBinding('jrn_$_a', '$_a$_a');
const _prompt = 'Keep this original prompt';

void main() {
  testWidgets('preflight precedes capture and references enter provider wire',
      (tester) async {
    final h = _Harness();
    await h.pump(tester);
    await _send(tester, _prompt);

    expect(h.paths.sublist(1), [
      '/api/context-memory/status',
      '/api/context-memory/preflight',
      '/api/context-memory/capture',
      '/v1/chat/completions',
    ]);
    final capture = h.body('/api/context-memory/capture');
    final event = capture['event'] as Map<String, dynamic>;
    final chat = h.body('/v1/chat/completions');
    final messages = chat['messages'] as List;
    final references = messages
        .whereType<Map>()
        .map((m) => '${m['content'] ?? ''}')
        .join('\n');

    expect(capture['project_ref'], 'mission-memory');
    expect(event['event_id'], chat['client_request_id']);
    expect(event['attempt_ref'], event['event_id']);
    expect(event['source_app'], 'flywheel-desktop');
    expect(event['conversation_ref'], 'c0');
    expect(event['session_id'], 'desktop-chat-c0');
    expect(event['message_text'], _prompt);
    expect(event.containsKey('hits'), isFalse);
    expect(messages.any((m) => (m as Map)['role'] == 'system'), isFalse);
    expect((messages.first as Map)['role'], 'user');
    expect(references, contains('Quoted Canon reference context'));
    expect(references, contains('project_ref=mission-memory'));
    expect(references, contains('record_id=prior-1'));
    expect(references, contains('claim_state=reported_by_source'));
    expect(references, contains('excerpt_truncated=false'));
    expect(references, contains('record_key=workspace/prior-1'));
    expect(references, contains('event_record_id=context-event-prior'));
    expect(references, contains('source_hash=$_b'));
    expect(references, contains('Previous native bridge choice'));
    expect((messages.last as Map)['content'], _prompt);
    expect(h.history.load().single.messages.first.text, _prompt);
    expect(find.textContaining('Canon context: returned 1 reference'),
        findsOneWidget);
  });

  testWidgets(
      'false successful preflight stays visible but does not block chat',
      (tester) async {
    final h = _Harness(preflight: const {'ok': true});
    await h.pump(tester);
    await _send(tester, _prompt);

    expect(h.paths, contains('/api/context-memory/capture'));
    expect(h.paths, contains('/v1/chat/completions'));
    final messages = h.body('/v1/chat/completions')['messages'] as List;
    expect(messages.any((m) => '${(m as Map)['content']}'.contains('Previous')),
        isFalse);
    expect(find.textContaining('Context search response was invalid'),
        findsOneWidget);
  });

  testWidgets('pending extraction status and coverage stay in provider wire',
      (tester) async {
    final h = _Harness(preflight: _pending());
    await h.pump(tester);
    await _send(tester, _prompt);

    final messages = h.body('/v1/chat/completions')['messages'] as List;
    final references =
        messages.map((m) => '${(m as Map)['content']}').join('\n');
    expect(references, contains('preflight_status=pending_extraction'));
    expect(references, contains('records_searched=1'));
    expect(references, contains('pending_count=1'));
    expect(references, contains('pending_returned=1'));
    expect(references, contains('source_freshness=unknown'));
    expect(references, contains('historical_completeness=unknown'));
    expect(references, contains('pending-event-1'));
    expect(references, contains('attachment-example-1'));
    expect(find.textContaining('pending extraction: 1 pending, 1 returned'),
        findsOneWidget);
  });

  testWidgets('capture denial shows status and preserves prompt dispatch',
      (tester) async {
    final h = _Harness(captureStatus: 403);
    await h.pump(tester);
    await _send(tester, _prompt);

    expect(h.paths, contains('/api/context-memory/preflight'));
    expect(h.paths, contains('/api/context-memory/capture'));
    expect(h.paths, contains('/v1/chat/completions'));
    expect(h.history.load().single.messages.first.text, _prompt);
    expect(find.textContaining('Canon capture failed'), findsOneWidget);
    expect(find.textContaining('gateway returned 403'), findsOneWidget);
  });

  testWidgets('capture false success remains visible without losing references',
      (tester) async {
    final h = _Harness(capture: _captureWithoutCanonReceipt());
    await h.pump(tester);
    await _send(tester, _prompt);

    final messages = h.body('/v1/chat/completions')['messages'] as List;
    final references =
        messages.map((m) => '${(m as Map)['content']}').join('\n');
    expect(references, contains('record_key=workspace/prior-1'));
    expect((messages.last as Map)['content'], _prompt);
    expect(find.textContaining('Capture response was invalid'), findsOneWidget);
  });

  testWidgets('first-message context failure remains visible in welcome state',
      (tester) async {
    final h = _Harness(preflight: const {'ok': true}, chatResponse: _emptySse);
    await h.pump(tester);
    await _send(tester, _prompt);

    expect(h.history.load(), isEmpty);
    expect(find.textContaining('Context search response was invalid'),
        findsOneWidget);
    expect(_editorText(tester), _prompt);
  });

  testWidgets('retained retry reuses capture identity and omits self-match',
      (tester) async {
    final h = _Harness(deniedAuthorizations: 1);
    await h.pump(tester);
    await _send(tester, _prompt);
    final first = h.bodiesFor('/api/context-memory/capture').single;
    final firstEvent = first['event'] as Map<String, dynamic>;
    final attemptRef = firstEvent['event_id'] as String;
    h.preflight
      ..clear()
      ..addAll(_found(hits: [
        _hit(
            recordId: 'self-1',
            excerpt: 'Self captured retry context',
            nativeId: attemptRef)
      ]));

    await _send(tester, _prompt);

    final captures = h.bodiesFor('/api/context-memory/capture');
    expect(captures, hasLength(2));
    expect(captures[1], first);
    final chat = h.body('/v1/chat/completions');
    expect(chat['client_request_id'], attemptRef);
    final messages = chat['messages'] as List;
    final context = (messages.first as Map)['content'] as String;
    expect(context, contains('current_submission_hits_omitted=1'));
    expect(context, contains('matching_records=1'));
    expect(context, isNot(contains('Self captured retry context')));
    expect((messages.last as Map)['content'], _prompt);
  });

  testWidgets('accepted same-text submission gets a new capture identity',
      (tester) async {
    final h = _Harness();
    await h.pump(tester);
    await _send(tester, _prompt);
    expect(h.history.load().single.messages.first.text, _prompt);
    await tester.pumpWidget(const SizedBox());
    await h.pump(tester);
    await _send(tester, _prompt);

    final captures = h.bodiesFor('/api/context-memory/capture');
    expect(captures, hasLength(2));
    final first = (captures[0]['event'] as Map)['event_id'];
    final second = (captures[1]['event'] as Map)['event_id'];
    expect(second, isNot(first));
  });

  testWidgets('changed retained draft gets a new capture identity',
      (tester) async {
    final h = _Harness(deniedAuthorizations: 1);
    await h.pump(tester);
    await _send(tester, _prompt);
    final first = h.bodiesFor('/api/context-memory/capture').single;
    await _send(tester, 'Changed prompt');

    final captures = h.bodiesFor('/api/context-memory/capture');
    expect(captures, hasLength(2));
    final firstEvent = first['event'] as Map;
    final secondEvent = captures[1]['event'] as Map;
    expect(secondEvent['event_id'], isNot(firstEvent['event_id']));
    expect(secondEvent['message_text'], 'Changed prompt');
  });

  testWidgets('missing Canon configuration keeps ordinary chat usable',
      (tester) async {
    final h = _Harness(status: _status(configured: false));
    await h.pump(tester);
    await _send(tester, _prompt);

    expect(h.paths, isNot(contains('/api/context-memory/preflight')));
    expect(h.paths, isNot(contains('/api/context-memory/capture')));
    expect(h.paths, contains('/v1/chat/completions'));
    expect(find.textContaining('Canon context not configured'), findsOneWidget);
  });

  testWidgets('dispose during context work immediately retains draft',
      (tester) async {
    final delayed = Completer<http.Response>();
    final h = _Harness(delayedPreflight: delayed.future);
    await h.pump(tester);
    await tester.enterText(find.byType(TextField), _prompt);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Send  (Enter)'));
    for (var i = 0;
        i < 8 && !h.paths.contains('/api/context-memory/preflight');
        i++) {
      await tester.pump(const Duration(milliseconds: 10));
    }

    expect(h.paths, contains('/api/context-memory/preflight'));
    await tester.pumpWidget(const SizedBox());
    var drafts = h.drafts.load();
    expect(drafts.single.text, _prompt);
    expect(drafts.single.state, ChatDraftState.retained);
    await h.pump(tester);
    expect(_editorText(tester), _prompt);
    delayed.complete(http.Response(jsonEncode(_found()), 200));
    await tester.pumpAndSettle();

    expect(h.paths, isNot(contains('/api/context-memory/capture')));
    expect(h.paths, isNot(contains('/v1/chat/completions')));
    drafts = h.drafts.load();
    expect(drafts.single.state, ChatDraftState.retained);
  });
}
