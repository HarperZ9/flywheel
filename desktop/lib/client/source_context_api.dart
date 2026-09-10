import 'dart:convert';

import 'gateway_client.dart';

const sourceContextRequestSchema = 'flywheel.source-context-request/v1';

abstract interface class SourceContextApi {
  Future<Map<String, dynamic>> inspect({
    required String rootMode,
    required String profile,
    required String corpus,
    Map<String, int> limits = const {},
  });

  Future<Map<String, dynamic>> select({
    required String rootMode,
    required String profile,
    required String corpus,
    required String expectedCorpusDigest,
    required List<Map<String, Object?>> selections,
    Map<String, int> limits = const {},
  });

  Future<Map<String, dynamic>> attach({
    required String rootMode,
    required String profile,
    required String corpus,
    required String expectedCorpusDigest,
    required List<Map<String, Object?>> selections,
    Map<String, int> limits = const {},
  });
}

final class GatewaySourceContextApi implements SourceContextApi {
  final GatewayClient _client;
  GatewaySourceContextApi(this._client);

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, Object?> body,
  ) async {
    if (utf8.encode(jsonEncode(body)).length > 1048576) {
      throw const FormatException('Source context request is too large.');
    }
    return _client.postJson(path, body);
  }

  Map<String, Object?> _request({
    required String rootMode,
    required String profile,
    required String corpus,
    Map<String, int> limits = const {},
    String? expectedCorpusDigest,
    List<Map<String, Object?>>? selections,
  }) => {
    'schema': sourceContextRequestSchema,
    'root_mode': rootMode,
    'profile': profile,
    'corpus': corpus,
    ...limits,
    if (expectedCorpusDigest != null)
      'expected_corpus_digest': expectedCorpusDigest,
    if (selections != null) 'selections': selections,
  };

  @override
  Future<Map<String, dynamic>> inspect({
    required String rootMode,
    required String profile,
    required String corpus,
    Map<String, int> limits = const {},
  }) => _post(
    '/api/source-context/inspect',
    _request(
      rootMode: rootMode,
      profile: profile,
      corpus: corpus,
      limits: limits,
    ),
  );

  @override
  Future<Map<String, dynamic>> select({
    required String rootMode,
    required String profile,
    required String corpus,
    required String expectedCorpusDigest,
    required List<Map<String, Object?>> selections,
    Map<String, int> limits = const {},
  }) => _post(
    '/api/source-context/select',
    _request(
      rootMode: rootMode,
      profile: profile,
      corpus: corpus,
      expectedCorpusDigest: expectedCorpusDigest,
      selections: selections,
      limits: limits,
    ),
  );

  @override
  Future<Map<String, dynamic>> attach({
    required String rootMode,
    required String profile,
    required String corpus,
    required String expectedCorpusDigest,
    required List<Map<String, Object?>> selections,
    Map<String, int> limits = const {},
  }) => _post(
    '/api/source-context/attach',
    _request(
      rootMode: rootMode,
      profile: profile,
      corpus: corpus,
      expectedCorpusDigest: expectedCorpusDigest,
      selections: selections,
      limits: limits,
    ),
  );
}
