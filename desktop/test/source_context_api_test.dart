import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/source_context_api.dart';

const _digest =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

GatewaySourceContextApi _api(
  Future<http.Response> Function(http.Request) handler,
) => GatewaySourceContextApi(
  GatewayClient(
    baseUrl: 'http://127.0.0.1:8799',
    httpClient: MockClient(handler),
  ),
);

void main() {
  test('inspect posts the admitted source context request', () async {
    final api = _api((request) async {
      expect(request.url.path, '/api/source-context/inspect');
      expect(jsonDecode(request.body), {
        'schema': sourceContextRequestSchema,
        'root_mode': 'flywheel_corpus',
        'profile': 'docs',
        'corpus': 'operator-notes',
        'max_rows': 12,
      });
      return http.Response(jsonEncode({'schema': 'ok'}), 200);
    });

    final out = await api.inspect(
      rootMode: 'flywheel_corpus',
      profile: 'docs',
      corpus: 'operator-notes',
      limits: const {'max_rows': 12},
    );

    expect(out['schema'], 'ok');
  });

  test('select binds the expected digest and selection list', () async {
    final selections = [
      {'path': 'notes.md', 'start': 1, 'end': 4},
    ];
    final api = _api((request) async {
      expect(request.url.path, '/api/source-context/select');
      expect(jsonDecode(request.body), {
        'schema': sourceContextRequestSchema,
        'root_mode': 'flywheel_corpus',
        'profile': 'docs',
        'corpus': 'operator-notes',
        'expected_corpus_digest': _digest,
        'selections': selections,
      });
      return http.Response(jsonEncode({'schema': 'ok'}), 200);
    });

    final out = await api.select(
      rootMode: 'flywheel_corpus',
      profile: 'docs',
      corpus: 'operator-notes',
      expectedCorpusDigest: _digest,
      selections: selections,
    );

    expect(out['schema'], 'ok');
  });

  test(
    'attach publishes the selected context through the source route',
    () async {
      final api = _api((request) async {
        expect(request.url.path, '/api/source-context/attach');
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['schema'], sourceContextRequestSchema);
        expect(body['expected_corpus_digest'], _digest);
        expect(body['selections'], isA<List<dynamic>>());
        return http.Response(jsonEncode({'schema': 'ok'}), 200);
      });

      final out = await api.attach(
        rootMode: 'flywheel_corpus',
        profile: 'docs',
        corpus: 'operator-notes',
        expectedCorpusDigest: _digest,
        selections: const [],
      );

      expect(out['schema'], 'ok');
    },
  );
}
