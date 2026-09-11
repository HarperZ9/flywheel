import '../models/agent_trace.dart';
import '../models/agent_trace_record.dart';

enum TraceReadFailure {
  unavailable,
  unauthorized,
  integrity,
  transport,
  limit,
  cancelled
}

final class TraceReadException implements Exception {
  final TraceReadFailure failure;
  const TraceReadException(this.failure);
  @override
  String toString() => 'Private trace read: ${failure.name}';
}

abstract interface class AgentTraceReader {
  Future<TracePage> read(TraceProjection projection, int sequence,
      {Future<void>? cancelled});
}
