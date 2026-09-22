import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:http/http.dart' as http;

void main() {
  test('chat stream preserves typed model selection required errors', () async {
    final client = GatewayClient(
      httpClient: _SingleResponseClient((request) async {
        expect(request.url.path, '/v1/chat/completions');
        final body = jsonEncode({
          'schema': gatewayErrorSchema,
          'error': {
            'code': 'MODEL_SELECTION_REQUIRED',
            'message': 'codex-cli requires an explicit model selection',
          },
        });
        return http.StreamedResponse(
          Stream<List<int>>.value(utf8.encode(body)),
          422,
          headers: {'content-type': 'application/json'},
        );
      }),
    );

    await expectLater(
      client.chatStream([
        {'role': 'user', 'content': 'hello'},
      ], 'codex-cli'),
      emitsError(isA<GatewayException>()
          .having((error) => error.statusCode, 'statusCode', 422)
          .having(
              (error) => error.errorSchema, 'errorSchema', gatewayErrorSchema)
          .having((error) => error.errorCode, 'errorCode',
              'MODEL_SELECTION_REQUIRED')),
    );
  });
}

final class _SingleResponseClient extends http.BaseClient {
  final Future<http.StreamedResponse> Function(http.BaseRequest request)
      handler;
  _SingleResponseClient(this.handler);

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      handler(request);
}
