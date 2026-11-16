part of 'gateway_client.dart';

extension GatewayInspectEvidence on GatewayClient {
  Future<InspectImportList> listInspectEvidenceImports({
    int limit = 10,
    int offset = 0,
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final safeLimit = limit < 1
        ? 1
        : limit > 50
            ? 50
            : limit;
    final query = {
      'limit': '$safeLimit',
      if (offset > 0) 'offset': '$offset',
    };
    final uri = Uri.parse('$baseUrl/api/import/inspect')
        .replace(queryParameters: query);
    final response = await _http.get(uri).timeout(timeout);
    return InspectImportList.fromJson(_inspectBody(response));
  }

  Future<InspectImportResult> readInspectEvidenceImport(
    String eid, {
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final encoded = Uri.encodeComponent(eid);
    final uri = Uri.parse('$baseUrl/api/import/inspect/$encoded');
    final response = await _http.get(uri).timeout(timeout);
    return InspectImportResult.fromJson(_inspectBody(response));
  }

  Future<InspectImportResult> uploadInspectEvidence(
    InspectEvidenceUpload upload, {
    required GatewayJourneyBinding binding,
    required String grantRef,
    Duration timeout = const Duration(seconds: 60),
  }) async {
    _validateInspectUpload(upload);
    final request =
        http.Request('POST', Uri.parse('$baseUrl/api/import/inspect'))
          ..headers['Content-Type'] = 'application/json'
          ..headers['Content-Length'] = '${upload.byteLength}'
          ..headers['X-Flywheel-Journey-Ref'] = binding.journeyRef
          ..headers['X-Flywheel-Expected-Event-Head'] = binding.eventHead
          ..headers['X-Flywheel-Client-Request-Id'] = upload.clientRequestId
          ..headers['X-Flywheel-Grant-Ref'] = grantRef
          ..headers['X-Flywheel-Inspect-Sha256'] = upload.sha256
          ..headers['X-Flywheel-Inspect-Byte-Length'] = '${upload.byteLength}';
    final filename = upload.filename;
    if (filename != null) {
      request.headers['X-Flywheel-Inspect-Filename'] = filename;
    }
    request.bodyBytes = upload.bytes;
    final response = await _sendInspectUpload(request, timeout);
    final result = InspectImportResult.fromJson(_inspectBody(response));
    if (!result.matchesUpload(upload)) {
      return const InspectImportResult.error(
        'SOURCE_DIGEST_MISMATCH',
        'Inspect import response did not match the uploaded bytes.',
      );
    }
    return result;
  }

  Future<http.Response> _sendInspectUpload(
    http.Request request,
    Duration timeout,
  ) async {
    final clock = Stopwatch()..start();
    try {
      final streamed = await _http.send(request).timeout(timeout);
      return await _responseFromStream(
        streamed,
        _remainingInspectTimeout(clock, timeout),
      );
    } on TimeoutException catch (error) {
      return http.Response(
        jsonEncode({
          'schema': gatewayErrorSchema,
          'error': {
            'code': 'GATEWAY_TIMEOUT',
            'message': error.message ?? 'Inspect import request timed out',
          },
        }),
        504,
        headers: {'content-type': 'application/json'},
        request: request,
      );
    }
  }

  Duration _remainingInspectTimeout(Stopwatch clock, Duration timeout) {
    final remaining = timeout - clock.elapsed;
    if (remaining <= Duration.zero) {
      throw TimeoutException('Inspect import request timed out', timeout);
    }
    return remaining;
  }

  Future<http.Response> _responseFromStream(
    http.StreamedResponse response,
    Duration timeout,
  ) {
    final body = BytesBuilder(copy: false);
    final completer = Completer<http.Response>();
    late StreamSubscription<List<int>> subscription;
    Timer? timer;

    void completeError(Object error, [StackTrace? stackTrace]) {
      if (completer.isCompleted) return;
      timer?.cancel();
      completer.completeError(error, stackTrace);
    }

    subscription = response.stream.listen(
      body.add,
      onError: completeError,
      onDone: () {
        if (completer.isCompleted) return;
        timer?.cancel();
        completer.complete(http.Response.bytes(
          body.takeBytes(),
          response.statusCode,
          request: response.request,
          headers: response.headers,
          isRedirect: response.isRedirect,
          persistentConnection: response.persistentConnection,
          reasonPhrase: response.reasonPhrase,
        ));
      },
      cancelOnError: true,
    );
    timer = Timer(timeout, () {
      if (completer.isCompleted) return;
      subscription.cancel().catchError((_) {});
      completer.completeError(
        TimeoutException(
          'Inspect import response body timed out',
          timeout,
        ),
      );
    });
    return completer.future.whenComplete(() => timer?.cancel());
  }

  void _validateInspectUpload(InspectEvidenceUpload upload) {
    if (upload.byteLength != upload.bytes.length || upload.byteLength < 1) {
      throw const InspectEvidenceUploadException(
        'INVALID_LENGTH',
        'Inspect upload length is invalid',
      );
    }
    if (upload.byteLength > maxInspectEvidenceUploadBytes) {
      throw const InspectEvidenceUploadException(
        'PAYLOAD_TOO_LARGE',
        'Inspect upload is over 16 MiB',
      );
    }
  }

  Map<String, Object?> _inspectBody(http.Response response) {
    Map<String, Object?>? decoded;
    try {
      final value = jsonDecode(response.body);
      if (value is Map) decoded = Map<String, Object?>.from(value);
    } on Object {
      // Fall through to a fixed transport envelope.
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      if (_hasErrorEnvelope(decoded)) return decoded!;
      return {
        'schema': gatewayErrorSchema,
        'error': {
          'code': 'GATEWAY_ERROR',
          'message': 'Inspect import request failed (${response.statusCode})',
        },
      };
    }
    if (decoded != null) return decoded;
    return {
      'schema': gatewayErrorSchema,
      'error': {
        'code': 'INVALID_RESPONSE',
        'message': 'Inspect import response was invalid',
      },
    };
  }

  bool _hasErrorEnvelope(Map<String, Object?>? decoded) {
    final error = decoded?['error'];
    return error is Map && error['code'] is String;
  }
}
