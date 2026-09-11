part of 'gateway_client.dart';

/// Reads private originals through the same authenticated transport as operations.
/// No action submission, redirect, export, or history registration occurs here.
final class GatewayAgentTrace implements AgentTraceReader {
  final GatewayClient _client;
  final Duration timeout;
  final int maxResponseBytes;

  GatewayAgentTrace(
    this._client, {
    this.timeout = const Duration(seconds: 30),
    this.maxResponseBytes = traceMaxResponseBytes,
  }) {
    if (timeout <= Duration.zero ||
        timeout > const Duration(seconds: 30) ||
        maxResponseBytes < 1 ||
        maxResponseBytes > traceMaxResponseBytes) {
      throw ArgumentError('Invalid private trace read bounds');
    }
  }

  @override
  Future<TracePage> read(TraceProjection projection, int sequence,
      {Future<void>? cancelled}) async {
    if (sequence < 0 || sequence >= projection.recordCount) {
      throw const TraceReadException(TraceReadFailure.integrity);
    }
    final abort = Completer<void>();
    void stop() {
      if (!abort.isCompleted) abort.complete();
    }

    cancelled?.then((_) => stop(), onError: (_) => stop());
    final uri = Uri.parse('${_client.baseUrl}/api/operations/'
            '${projection.operationRef}/trace')
        .replace(queryParameters: {
      'ref': projection.traceRef,
      'sequence': '$sequence',
    });
    final request =
        http.AbortableRequest('GET', uri, abortTrigger: abort.future)
          ..followRedirects = false
          ..headers['Accept'] = 'application/json';
    final elapsed = Stopwatch()..start();
    try {
      final page = await Future.any([
        _read(request, projection, sequence),
        abort.future.then<TracePage>(
            (_) => throw const TraceReadException(TraceReadFailure.cancelled)),
      ]).timeout(timeout);
      // Synchronous decoding must not let a late completion outrun the timer.
      if (elapsed.elapsed > timeout) {
        throw const TraceReadException(TraceReadFailure.transport);
      }
      return page;
    } on TraceReadException {
      rethrow;
    } on TraceLimitException {
      throw const TraceReadException(TraceReadFailure.limit);
    } on FormatException {
      throw const TraceReadException(TraceReadFailure.integrity);
    } catch (_) {
      // Neither private error bodies nor parser source text reaches the UI/logs.
      throw const TraceReadException(TraceReadFailure.transport);
    } finally {
      stop();
    }
  }

  Future<TracePage> _read(http.BaseRequest request, TraceProjection projection,
      int sequence) async {
    final response = await _client._http.send(request);
    if (response.statusCode != 200) {
      throw TraceReadException(switch (response.statusCode) {
        401 => TraceReadFailure.unauthorized,
        404 => TraceReadFailure.unavailable,
        422 || 500 => TraceReadFailure.integrity,
        _ => TraceReadFailure.transport,
      });
    }
    if ((response.contentLength ?? 0) > maxResponseBytes) {
      throw const TraceReadException(TraceReadFailure.limit);
    }
    final bytes = BytesBuilder(copy: false);
    await for (final chunk in response.stream) {
      if (bytes.length + chunk.length > maxResponseBytes) {
        throw const TraceReadException(TraceReadFailure.limit);
      }
      bytes.add(chunk);
    }
    return TracePage.fromJson(
        traceJsonObject(bytes.takeBytes(),
            maxBytes: maxResponseBytes, maxDepth: 34),
        operationRef: projection.operationRef,
        journeyRef: projection.journeyRef,
        traceRef: projection.traceRef,
        sequence: sequence);
  }
}
