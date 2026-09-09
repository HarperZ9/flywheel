import 'dart:convert';
import 'dart:io';

import 'bulletin_media_test_support.dart';

final class CanonicalBackend {
  final HttpServer server;
  final List<String> paths = [];
  final List<Map<String, Object?>> requestBodies = [];

  CanonicalBackend(this.server);

  String get baseUrl => 'http://127.0.0.1:${server.port}';
  Future<void> close() => server.close(force: true);
}

Future<CanonicalBackend> startCanonicalBackend({
  required String runId,
  required String title,
  Map<String, Object?>? credentialHandleResponse,
}) async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  final backend = CanonicalBackend(server);
  server.listen((request) async {
    final raw = await utf8.decoder.bind(request).join();
    backend.paths.add(request.uri.path);
    backend.requestBodies.add(Map<String, Object?>.from(
        raw.isEmpty ? const {} : jsonDecode(raw) as Map<String, dynamic>));
    request.response.headers.contentType = ContentType.json;
    switch (request.uri.path) {
      case '/api/gateway-grants/bulletin-media-runs':
        request.response
            .write(jsonEncode(runsResponseJson(runId: runId, title: title)));
        break;
      case '/api/gateway-grants/bulletin-media-artifacts':
        request.response.write(jsonEncode(artifactsResponseJson(runId: runId)));
        break;
      case '/api/credential-handles':
        request.response.write(jsonEncode(credentialHandleResponse ??
            {
              'schema': 'flywheel.credential-handle-list/v1',
              'handles': [
                {
                  'credential_ref': credRef,
                  'credential_name': 'BULLETIN_AGENT_JWK'
                }
              ]
            }));
        break;
      default:
        request.response.statusCode = 404;
        request.response.write(jsonEncode({'error': 'unexpected route'}));
    }
    await request.response.close();
  });
  return backend;
}
