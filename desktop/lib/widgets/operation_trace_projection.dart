import '../models/agent_trace.dart';
import '../models/operation_models.dart';

final class OperationTraceProjectionException implements Exception {
  final String message;
  const OperationTraceProjectionException(this.message);
}

TraceProjection? acceptedOperationTraceProjection({
  required OperationSnapshot snapshot,
  required OperationResult? result,
  required List<Map<String, dynamic>> progress,
}) {
  Map<String, dynamic>? raw;
  if (result != null && result.result['schema'] == traceProjectionSchema) {
    if (result.operationRef != snapshot.operationRef ||
        result.state != snapshot.state ||
        result.canonicalSha256 != snapshot.resultSha256) {
      throw const OperationTraceProjectionException(
          'Private trace unavailable: operation result did not match.');
    }
    raw = Map<String, dynamic>.from(result.result);
  } else if (!snapshot.isTerminal) {
    for (final event in progress.reversed) {
      if (event['schema'] == traceProjectionSchema) {
        raw = event;
        break;
      }
    }
  }
  if (raw == null) return null;
  try {
    final projection = TraceProjection.fromJson(raw,
        operationRef: snapshot.operationRef, journeyRef: snapshot.journeyRef);
    if ((snapshot.isTerminal && projection.state != result?.state.name) ||
        (!snapshot.isTerminal && !projection.isRunning)) {
      invalidTrace();
    }
    return projection;
  } on Object {
    throw const OperationTraceProjectionException(
        'Private trace unavailable: metadata did not match.');
  }
}
