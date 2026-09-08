import 'dart:convert';

import '../models/continuation_models.dart';
import 'gateway_client.dart';

abstract interface class ContinuationApi {
  Future<ContinuationPreview> preview(
      {required String root, String? exportPath});
  Future<ContinuationPrivateContext> privateContext(
      ContinuationPreview preview);
  Future<ContinuationStartResult> start(ContinuationPreview preview);
  Future<ContinuationUndoResult> undo({
    required String journeyRef,
    required String expectedEventHead,
    required ContinuationPreview preview,
  });
}

const _fixed = <String, String>{
  'SOURCE_DRIFT': 'Source changed since preview; preview again.',
  'PREVIEW_NOT_FOUND': 'Continuation preview was not found.',
  'PREVIEW_MISMATCH': 'Continuation preview does not match this request.',
  'INVALID_CONTINUATION': 'Continuation request is invalid.',
  'CONTINUATION_BLOCKED': 'Continuation source is incomplete.',
  'ROOT_UNAVAILABLE': 'Workspace root is unavailable.',
  'UNKNOWN_FIELD': 'Continuation request contains unsupported fields.',
  'MISSING_FIELD': 'Continuation request is missing required fields.',
};

ContinuationFailure _failure(Object? error) {
  if (error is GatewayException && error.errorSchema == gatewayErrorSchema) {
    final code = error.errorCode;
    if (code != null && _fixed.containsKey(code)) {
      return ContinuationFailure(code, _fixed[code]!);
    }
  }
  return const ContinuationFailure(
      'INVALID_RESPONSE', 'Continuation response was invalid.');
}

class GatewayContinuationApi implements ContinuationApi {
  final GatewayClient _client;
  GatewayContinuationApi(this._client);

  Future<Map<String, dynamic>> _post(
      String path, Map<String, dynamic> body) async {
    try {
      if (utf8.encode(jsonEncode(body)).length > 1048576) {
        throw const ContinuationApiException(ContinuationFailure(
            'INVALID_RESPONSE', 'Continuation request was too large.'));
      }
      return await _client.postJson(path, body);
    } on ContinuationApiException {
      rethrow;
    } on Object catch (error) {
      throw ContinuationApiException(_failure(error));
    }
  }

  @override
  Future<ContinuationPreview> preview(
      {required String root, String? exportPath}) async {
    final result =
        ContinuationPreview.fromJson(await _post('/api/continuation/preview', {
      'root': root,
      if (exportPath != null && exportPath.isNotEmpty)
        'export_path': exportPath,
    }));
    if (result.invalidResponse) throw ContinuationApiException(_failure(null));
    return result;
  }

  @override
  Future<ContinuationStartResult> start(ContinuationPreview preview) async {
    final result = ContinuationStartResult.fromJson(
        await _post('/api/continuation/start', {
      'preview_ref': preview.previewRef,
      'preview_sha256': preview.previewSha256,
      'source_state_sha256': preview.sourceStateSha256,
      'client_request_id': 'continuation-start-${preview.previewRef}',
    }));
    if (result.invalidResponse) throw ContinuationApiException(_failure(null));
    return result;
  }

  @override
  Future<ContinuationPrivateContext> privateContext(
      ContinuationPreview preview) async {
    final result = ContinuationPrivateContext.fromJson(
        await _post('/api/continuation/context', {
      'preview_ref': preview.previewRef,
      'preview_sha256': preview.previewSha256,
      'source_state_sha256': preview.sourceStateSha256,
    }));
    if (result.invalidResponse) throw ContinuationApiException(_failure(null));
    return result;
  }

  @override
  Future<ContinuationUndoResult> undo({
    required String journeyRef,
    required String expectedEventHead,
    required ContinuationPreview preview,
  }) async {
    final result =
        ContinuationUndoResult.fromJson(await _post('/api/continuation/undo', {
      'journey_ref': journeyRef,
      'expected_event_head': expectedEventHead,
      'preview_ref': preview.previewRef,
      'preview_sha256': preview.previewSha256,
      'client_request_id':
          'continuation-undo-${preview.previewRef}-$journeyRef-$expectedEventHead',
    }));
    if (result.invalidResponse) throw ContinuationApiException(_failure(null));
    return result;
  }
}
