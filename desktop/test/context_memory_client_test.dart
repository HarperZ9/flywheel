import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';

void main() {
  test('scope refusal remains an error rather than an empty search', () async {
    final client = GatewayClient(httpClient: MockClient((request) async {
      return http.Response(
          jsonEncode({
            'schema': gatewayErrorSchema,
            'error': {
              'code': 'CONTEXT_OWNER_NOT_BOUND',
              'message': 'gateway owner is not bound to this Canon scope',
            },
          }),
          403);
    }));
    await expectLater(
      client.contextMemoryPreflight(projectRef: 'mission', query: 'prior work'),
      throwsA(isA<GatewayException>()
          .having((error) => error.statusCode, 'HTTP status', 403)
          .having((error) => error.errorCode, 'refusal',
              'CONTEXT_OWNER_NOT_BOUND')),
    );
  });

  test(
    'context memory client names status capture and preflight routes',
    () async {
      final seen = <String, Object?>{};
      final client = GatewayClient(
        baseUrl: 'http://127.0.0.1:8799',
        httpClient: MockClient((request) async {
          seen[request.url.path] = jsonDecode(request.body);
          return http.Response(jsonEncode({'schema': 'ok'}), 200);
        }),
      );

      await client.contextMemoryStatus();
      await client.contextMemoryCapture(
        projectRef: 'mission-memory',
        event: const {
          'event_id': 'turn-1',
          'message_text': 'Build native bridge',
        },
      );
      await client.contextMemoryPreflight(
        projectRef: 'mission-memory',
        query: 'native bridge',
        topK: 3,
        includePendingExtraction: false,
      );

      expect(seen, {
        '/api/context-memory/status': {},
        '/api/context-memory/capture': {
          'schema': contextMemoryCaptureRequestSchema,
          'project_ref': 'mission-memory',
          'event': {
            'event_id': 'turn-1',
            'message_text': 'Build native bridge',
          },
        },
        '/api/context-memory/preflight': {
          'schema': contextMemoryPreflightRequestSchema,
          'project_ref': 'mission-memory',
          'query': 'native bridge',
          'top_k': 3,
          'include_pending_extraction': false,
        },
      });
    },
  );
}
