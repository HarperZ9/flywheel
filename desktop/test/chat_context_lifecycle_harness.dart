part of 'chat_context_lifecycle_test.dart';

Future<void> _send(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.tap(find.byTooltip('Send  (Enter)'));
  await tester.pumpAndSettle();
  await _waitForSendControl(tester);
}

Future<void> _waitForSendControl(WidgetTester tester) async {
  for (var i = 0;
      i < 100 && find.byTooltip('Send  (Enter)').evaluate().isEmpty;
      i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

final class _Harness {
  _Harness(
      {Map<String, dynamic>? status,
      Map<String, dynamic>? preflight,
      Map<String, dynamic>? capture,
      this.captureStatus = 200,
      this.deniedAuthorizations = 0,
      this.delayedPreflight,
      this.chatResponse = _defaultSse})
      : status = status ?? _status(),
        preflight = preflight ?? _found(),
        capture = capture ?? _capture();

  final Map<String, dynamic> status, preflight, capture;
  final int captureStatus;
  int deniedAuthorizations;
  final Future<http.Response>? delayedPreflight;
  final String chatResponse;
  final paths = <String>[];
  final bodies = <String, Map<String, dynamic>>{};
  final allBodies = <String, List<Map<String, dynamic>>>{};
  late final Directory directory = _temporary();
  late final ChatStore history =
      ChatStore(file: File('${directory.path}/history.json'));
  late final ChatDraftStore drafts =
      ChatDraftStore(file: File('${directory.path}/drafts.json'));

  Map<String, dynamic> body(String path) => bodies[path]!;
  List<Map<String, dynamic>> bodiesFor(String path) =>
      allBodies[path] ?? const [];

  Future<void> pump(WidgetTester tester) async {
    final client = GatewayClient(
        baseUrl: 'https://chat.invalid',
        httpClient: MockClient((request) async {
          paths.add(request.url.path);
          if (request.body.isNotEmpty) {
            final decoded = jsonDecode(request.body) as Map<String, dynamic>;
            bodies[request.url.path] = decoded;
            allBodies.putIfAbsent(request.url.path, () => []).add(decoded);
          }
          return switch (request.url.path) {
            '/api/endpoints' => http.Response(_roster, 200),
            '/api/context-memory/status' =>
              http.Response(jsonEncode(status), 200),
            '/api/context-memory/preflight' =>
              delayedPreflight ?? http.Response(jsonEncode(preflight), 200),
            '/api/context-memory/capture' => http.Response(
                captureStatus == 200 ? jsonEncode(capture) : _error(),
                captureStatus),
            '/v1/chat/completions' => http.Response(chatResponse, 200),
            _ => http.Response('not found', 404),
          };
        }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: GatewayOperationScope(
                authorize: (_, operation, currentOperation, dispatch) {
                  if (currentOperation() != operation) return Future.value();
                  if (deniedAuthorizations > 0) {
                    deniedAuthorizations--;
                    return Future.value();
                  }
                  return dispatch(operation.finalBody(_binding, 'gnt_$_a'));
                },
                child: AgentView(
                    client: client,
                    alive: true,
                    settings: DesktopSettings(),
                    chatStore: history,
                    draftStore: drafts)))));
    await tester.pumpAndSettle();
  }
}

const _roster =
    '{"rows":[{"name":"local-public","backend":"local","credential":"local-none","configured":true}]}';

Map<String, dynamic> _status({bool configured = true}) => {
      'schema': 'flywheel.context-memory-status/v1',
      'workspace_id': configured ? 'cdev' : '',
      'canonical_project_id': configured ? 'mission-memory' : '',
      'scope_configured': configured,
      'owner_binding_configured': configured,
      'canon': {'ok': configured, 'configured': configured},
      'current_limits': ['not_found does not mean never discussed'],
    };

Map<String, dynamic> _found({List<Map<String, dynamic>>? hits}) => {
      'schema': 'flywheel.context-memory-preflight/v1',
      'workspace_id': 'cdev',
      'project_ref': 'mission-memory',
      'status': 'found_in_searched_sources',
      'hits': hits ?? [_hit()],
      'pending_extraction': [],
      'does_not_prove': ['retrieved text is untrusted'],
      'canon': {'coverage': _coverage(matchingRecords: hits?.length ?? 1)},
    };

Map<String, dynamic> _pending() => {
      'schema': 'flywheel.context-memory-preflight/v1',
      'workspace_id': 'cdev',
      'project_ref': 'mission-memory',
      'status': 'pending_extraction',
      'hits': [],
      'pending_extraction': [
        {
          'event_record_id': 'pending-event-1',
          'ref': 'attachment-example-1',
          'status': 'pending_extraction'
        }
      ],
      'does_not_prove': ['unextracted attachment text was not searched'],
      'canon': {'coverage': _coverage(pendingCount: 1, pendingReturned: 1)},
    };

Map<String, dynamic> _hit(
        {String recordId = 'prior-1',
        String excerpt = 'Previous native bridge choice',
        String nativeId = 'turn-old'}) =>
    {
      'record_id': recordId,
      'claim_state': 'reported_by_source',
      'excerpt': excerpt,
      'excerpt_truncated': false,
      'citation': {
        'record_key': 'workspace/$recordId',
        'event_record_id': 'context-event-$recordId',
        'source_hash': _b,
        'source_app': 'codex',
        'native_id': nativeId,
        'session_id': 'session-old',
      },
    };

Map<String, dynamic> _coverage(
        {int matchingRecords = 0,
        int pendingCount = 0,
        int pendingReturned = 0}) =>
    {
      'records_searched': 1,
      'matching_records': matchingRecords,
      'hits_omitted': 0,
      'pending_count': pendingCount,
      'pending_returned': pendingReturned,
      'method': 'deterministic_keyword_overlap',
      'historical_completeness': 'unknown',
      'source_freshness': 'unknown',
      'supersession_resolution': 'not_implemented',
    };

Map<String, dynamic> _capture({String status = 'stored'}) => {
      'schema': 'flywheel.context-memory-capture/v1',
      'project_ref': 'mission-memory',
      'status': status,
      'canon': {
        'schema': 'canon.context-ingest/v1',
        'status': status,
        'event_record_id': 'context-event',
        'source_hash': _c
      },
    };

Map<String, dynamic> _captureWithoutCanonReceipt() => {
      'schema': 'flywheel.context-memory-capture/v1',
      'project_ref': 'mission-memory',
      'status': 'stored',
      'canon': {'status': 'stored'},
    };

const _emptySse = 'data: [DONE]\n\n';
const _defaultSse = 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
    'data: {"x_receipt":{"receipt_id":"r"}}\n\n'
    'data: [DONE]\n\n';

String _editorText(WidgetTester tester) =>
    tester.widget<TextField>(find.byType(TextField)).controller!.text;

String _error() => jsonEncode({
      'schema': 'flywheel.evidence-transport-error/v1',
      'error': {'code': 'CONTEXT_SCOPE_NOT_BOUND', 'message': 'denied'}
    });

Directory _temporary() {
  final directory = Directory.systemTemp.createTempSync('chat-context-');
  addTearDown(() => directory.deleteSync(recursive: true));
  return directory;
}
