part of 'gateway_client.dart';

extension GatewayProcessAuditReview on GatewayClient {
  Future<ProcessAuditReviewResult> reviewProcessAuditPacket(
    ProcessAuditPacketUpload upload, {
    Duration timeout = const Duration(seconds: 60),
  }) async {
    if (upload.byteLength != upload.bytes.length || upload.byteLength < 1) {
      throw const ProcessAuditReviewException(
        'INVALID_LENGTH',
        'Process-audit upload length is invalid.',
      );
    }
    if (upload.byteLength > maxProcessAuditPacketBytes) {
      throw const ProcessAuditReviewException(
        'PAYLOAD_TOO_LARGE',
        'Process-audit packet bytes are over 1 MiB.',
      );
    }
    final request = http.Request(
      'POST',
      Uri.parse('$baseUrl/api/incident-sim/process-audit/review'),
    )
      ..headers['Content-Type'] = 'application/json'
      ..headers['Content-Length'] = '${upload.byteLength}'
      ..bodyBytes = upload.bytes;
    try {
      final streamed = await _http.send(request).timeout(timeout);
      final response =
          await http.Response.fromStream(streamed).timeout(timeout);
      return ProcessAuditReviewResult.fromJson(
        _processAuditBody(response),
        upload,
      );
    } on TimeoutException catch (error) {
      return ProcessAuditReviewResult.error(
        'GATEWAY_TIMEOUT',
        error.message ?? 'Process-audit review timed out.',
      );
    }
  }

  Map<String, Object?> _processAuditBody(http.Response response) {
    Map<String, Object?>? decoded;
    try {
      final value = jsonDecode(response.body);
      if (value is Map) decoded = Map<String, Object?>.from(value);
    } on Object {
      // Fixed envelope below.
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      if (_hasProcessAuditError(decoded)) return decoded!;
      return {
        'schema': gatewayErrorSchema,
        'error': {
          'code': 'GATEWAY_ERROR',
          'message': 'Process-audit review failed (${response.statusCode})',
        },
      };
    }
    if (decoded != null) return decoded;
    return {
      'schema': gatewayErrorSchema,
      'error': {
        'code': 'INVALID_RESPONSE',
        'message': 'Process-audit review response was invalid',
      },
    };
  }

  bool _hasProcessAuditError(Map<String, Object?>? decoded) {
    final error = decoded?['error'];
    return error is Map && error['code'] is String;
  }
}
