import 'dart:async';
import 'package:flutter/foundation.dart';
import '../client/agent_trace_reader.dart';
import '../models/agent_trace.dart';
import '../models/agent_trace_record.dart';

/// Keeps an explicitly requested prefix in memory for this private viewer only.
final class AgentTraceController extends ChangeNotifier {
  final AgentTraceReader reader;
  final TraceProjection projection;
  final List<TraceRecord> _records = [];
  final Completer<void> _cancelled = Completer<void>();
  int _bytes = 0;
  bool _disposed = false, _loading = false;
  TraceReadFailure? _failure;

  AgentTraceController(this.reader, this.projection);
  List<TraceRecord> get records => List.unmodifiable(_records);
  bool get loading => _loading;
  bool get complete => _records.length == projection.recordCount;
  TraceReadFailure? get failure => _failure;

  Future<void> loadNext() async {
    if (_disposed || _loading || complete) return;
    _loading = true;
    _failure = null;
    notifyListeners();
    try {
      final page = await reader.read(projection, _records.length,
          cancelled: _cancelled.future);
      if (_disposed) return;
      final record = page.record;
      final terminal = !projection.isRunning;
      if (record.sequence != _records.length ||
          record.operationRef != projection.operationRef ||
          record.journeyRef != projection.journeyRef ||
          record.traceRef != projection.traceRef ||
          record.priorSha256 !=
              (_records.isEmpty ? traceGenesis : _records.last.recordSha256) ||
          (_records.isNotEmpty && record.ownerRef != _records.first.ownerRef) ||
          page.recordCount < projection.recordCount ||
          (terminal &&
              (page.recordCount != projection.recordCount ||
                  page.traceHeadSha256 != projection.traceHeadSha256)) ||
          (record.sequence == projection.recordCount - 1 &&
              record.recordSha256 != projection.traceHeadSha256)) {
        throw const TraceReadException(TraceReadFailure.integrity);
      }
      if (_bytes + record.byteCount > traceMaxBytes) {
        throw const TraceReadException(TraceReadFailure.limit);
      }
      _bytes += record.byteCount;
      _records.add(record);
    } on TraceReadException catch (error) {
      if (!_disposed) _failure = error.failure;
    } catch (_) {
      if (!_disposed) _failure = TraceReadFailure.integrity;
    } finally {
      if (!_disposed) {
        _loading = false;
        notifyListeners();
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _cancelled.complete();
    _records.clear();
    super.dispose();
  }
}
