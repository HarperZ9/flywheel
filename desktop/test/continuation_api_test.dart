import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/continuation_api.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/continuation_models.dart';

const _previewRef = 'cpv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _journeyRef = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _shaA =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _shaB =
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';

Map<String, Object?> _previewJson() => {
  'schema': 'flywheel.native-continuation-preview/v1',
  'preview_ref': _previewRef,
  'preview_sha256': _shaA,
  'source_state_sha256': _shaB,
  'intake_ref': 'continuation/$_previewRef.intake.json',
  'source': {'root': r'C:\work\repo', 'export_path': r'C:\work\export.jsonl'},
  'repo': {'branch': 'main', 'head': _shaA, 'dirty_files': const []},
  'import': {'mappings': const [], 'dropped': const [], 'mcp_server_count': 0},
  'export': {'signals': const []},
  'context_package': {
    'schema': 'flywheel.native-continuation-context/v1',
    'selected_tasks': ['Fix the parser'],
    'selected_summaries': const [],
    'selected_files': ['lib/parser.dart'],
    'commits': const [],
  },
  'runner_context': {
    'schema': 'flywheel.native-continuation-runner-context/v1',
    'root': r'C:\\work\\repo',
    'goal': 'Continue with private context.',
    'selected_files': ['lib/parser.dart'],
  },
  'provider_native_resume': {
    'state': 'unavailable',
    'reason': 'provider-native resume is not claimed',
  },
  'health': {'state': 'ready', 'blocking_omissions': const []},
  'omissions': const [],
};

Map<String, Object?> _ackJson({bool replay = false}) => {
  'schema': 'flywheel.evidence-journey-mutation-ack/v2',
  'journey_ref': _journeyRef,
  'event_head_sha256': _shaB,
  'event_sha256': _shaB,
  'projection_sha256': _shaA,
  'idempotent_replay': replay,
};

GatewayContinuationApi _api(
  Future<http.Response> Function(http.Request) handler,
) => GatewayContinuationApi(
  GatewayClient(
    baseUrl: 'http://127.0.0.1:8799',
    httpClient: MockClient(handler),
  ),
);

ContinuationPreview _preview() => ContinuationPreview.fromJson(_previewJson());

void main() {
  test('preview posts selected local root and export path', () async {
    final api = _api((request) async {
      expect(request.url.path, '/api/continuation/preview');
      expect(jsonDecode(request.body), {
        'root': r'C:\work\repo',
        'export_path': r'C:\work\export.jsonl',
      });
      return http.Response(jsonEncode(_previewJson()), 200);
    });

    final preview = await api.preview(
      root: r'C:\work\repo',
      exportPath: r'C:\work\export.jsonl',
    );

    expect(preview.previewRef, _previewRef);
    expect(preview.readyToStart, isTrue);
  });

  test('start retries reuse preview-bound idempotency key', () async {
    final bodies = <Map<String, dynamic>>[];
    final api = _api((request) async {
      expect(request.url.path, '/api/continuation/start');
      bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
      return http.Response(
        jsonEncode({
          'schema': 'flywheel.native-continuation-start/v1',
          'preview_ref': _previewRef,
          'open_lens': 'Rescue',
          'journey': _ackJson(replay: bodies.length > 1),
        }),
        200,
      );
    });

    await api.start(_preview());
    await api.start(_preview());

    expect(bodies, hasLength(2));
    expect(bodies.first, bodies.last);
    expect(
      bodies.first['client_request_id'],
      'continuation-start-$_previewRef',
    );
  });

  test('private context request is bound to preview hashes', () async {
    final api = _api((request) async {
      expect(request.url.path, '/api/continuation/context');
      expect(jsonDecode(request.body), {
        'preview_ref': _previewRef,
        'preview_sha256': _shaA,
        'source_state_sha256': _shaB,
      });
      return http.Response(
        jsonEncode({
          'schema': 'flywheel.native-continuation-private-context/v1',
          'preview_ref': _previewRef,
          'source_state_sha256': _shaB,
          'context_package': {
            'selected_tasks': ['Fix the parser'],
            'selected_files': ['lib/parser.dart'],
          },
          'runner_context': {
            'root': r'C:\\work\\repo',
            'goal': 'Continue with private context.',
            'selected_files': ['lib/parser.dart'],
          },
        }),
        200,
      );
    });

    final context = await api.privateContext(_preview());

    expect(context.previewRef, _previewRef);
    expect(context.runner.root, r'C:\\work\\repo');
    expect(context.runner.goal, contains('private context'));
    expect(context.selectedTaskCount, 1);
    expect(context.runner.selectedFiles, ['lib/parser.dart']);
    expect(context.agentHandoff(_preview()), {
      'schema': continuationAgentHandoffSchema,
      'preview_ref': _previewRef,
      'preview_sha256': _shaA,
      'source_state_sha256': _shaB,
      'selected_files': ['lib/parser.dart'],
    });
  });

  test(
    'undo retries bind idempotency key to preview journey and head',
    () async {
      final bodies = <Map<String, dynamic>>[];
      final api = _api((request) async {
        expect(request.url.path, '/api/continuation/undo');
        bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
        return http.Response(
          jsonEncode({
            'schema': 'flywheel.native-continuation-undo/v1',
            'preview_ref': _previewRef,
            'journey': _ackJson(replay: bodies.length > 1),
          }),
          200,
        );
      });

      await api.undo(
        journeyRef: _journeyRef,
        expectedEventHead: _shaB,
        preview: _preview(),
      );
      await api.undo(
        journeyRef: _journeyRef,
        expectedEventHead: _shaB,
        preview: _preview(),
      );

      expect(bodies, hasLength(2));
      expect(bodies.first, bodies.last);
      expect(
        bodies.first['client_request_id'],
        'continuation-undo-$_previewRef-$_journeyRef-$_shaB',
      );
    },
  );

  test('known route failures surface fixed copy', () async {
    final api = _api((request) async {
      return http.Response(
        jsonEncode({
          'schema': 'flywheel.evidence-transport-error/v1',
          'error': {'code': 'SOURCE_DRIFT', 'message': 'changed'},
        }),
        409,
      );
    });

    expect(
      () => api.start(_preview()),
      throwsA(
        isA<ContinuationApiException>().having(
          (error) => error.failure.message,
          'message',
          'Source changed since preview; preview again.',
        ),
      ),
    );
  });
}
