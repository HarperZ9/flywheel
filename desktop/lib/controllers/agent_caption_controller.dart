import 'dart:async';
import 'package:flutter/foundation.dart';
import '../client/agent_trace_reader.dart';
import '../models/agent_caption.dart';
import '../models/agent_trace.dart';
import '../models/agent_trace_record.dart';

/// Follows accepted metadata with private GETs; never controls task execution.
final class AgentCaptionController extends ChangeNotifier {
  final AgentTraceReader reader;
  final DateTime Function() _clock;
  TraceProjection _projection;
  final List<AgentCaption> _captions = [];
  final Map<int, String> _anchors = {};
  Completer<void>? _cancelled;
  bool _active = false, _following = true, _reading = false, _disposed = false;
  int _generation = 0, _sequence = 0, _bytes = 0, _uncaptioned = 0;
  String _head = traceGenesis;
  String? _owner;
  TraceReadFailure? _failure;
  bool _invalidBinding = false;

  AgentCaptionController(
      {required this.reader,
      required TraceProjection projection,
      DateTime Function()? clock})
      : _projection = projection,
        _clock = clock ?? DateTime.now;
  TraceProjection get projection => _projection;
  List<AgentCaption> get captions => List.unmodifiable(_captions);
  bool get active => _active;
  bool get following => _following;
  bool get reading => _reading;
  bool get caughtUp => _sequence == _projection.recordCount;
  int get readCount => _sequence;
  int get uncaptionedRecords => _uncaptioned;
  TraceReadFailure? get failure => _failure;
  bool get providerSummaryAvailable =>
      _captions.any((c) => c.kind == CaptionKind.providerSummary);

  Future<void> start() async {
    if (_disposed || _active || _invalidBinding) return;
    _active = true;
    _failure = null;
    _cancelled = Completer<void>();
    _anchors[_projection.recordCount] = _projection.traceHeadSha256;
    await _drain();
  }

  Future<void> updateProjection(TraceProjection next) async {
    if (_disposed || _invalidBinding) return;
    final current = _projection;
    if (next.operationRef != current.operationRef ||
        next.journeyRef != current.journeyRef ||
        next.traceRef != current.traceRef ||
        next.recordCount < current.recordCount ||
        (!current.isRunning &&
            next.projectionSha256 != current.projectionSha256) ||
        (next.recordCount == current.recordCount &&
            next.traceHeadSha256 != current.traceHeadSha256)) {
      close();
      _invalidBinding = true;
      _failure = TraceReadFailure.integrity;
      notifyListeners();
      return;
    }
    _projection = next;
    _anchors[next.recordCount] = next.traceHeadSha256;
    if (_sequence == next.recordCount && _head != next.traceHeadSha256) {
      close();
      _invalidBinding = true;
      _failure = TraceReadFailure.integrity;
      notifyListeners();
      return;
    }
    if (_active && _failure == null) await _drain();
  }

  void setFollowing(bool value) {
    if (_disposed || _following == value) return;
    _following = value;
    notifyListeners();
  }

  Future<void> retry() async {
    if (!_active || _disposed || _reading) return;
    _failure = _invalidBinding ? TraceReadFailure.integrity : null;
    await _drain();
  }

  Future<void> _drain() async {
    if (_reading || !_active || _disposed) return;
    _reading = true;
    final generation = _generation;
    notifyListeners();
    try {
      while (_active && !_disposed && generation == _generation && !caughtUp) {
        final target = _projection;
        final page =
            await reader.read(target, _sequence, cancelled: _cancelled!.future);
        if (!_active || _disposed || generation != _generation) return;
        _accept(page, target);
        notifyListeners();
      }
    } on TraceReadException catch (error) {
      if (!_disposed && generation == _generation) _failure = error.failure;
    } catch (_) {
      if (!_disposed && generation == _generation) {
        _failure = TraceReadFailure.integrity;
      }
    } finally {
      if (!_disposed && generation == _generation) {
        _reading = false;
        notifyListeners();
      }
    }
  }

  void _accept(TracePage page, TraceProjection target) {
    final record = page.record;
    final anchor = _anchors[_sequence + 1];
    if (record.sequence != _sequence ||
        record.priorSha256 != _head ||
        record.operationRef != target.operationRef ||
        record.journeyRef != target.journeyRef ||
        record.traceRef != target.traceRef ||
        (_owner != null && _owner != record.ownerRef) ||
        page.recordCount < target.recordCount ||
        (!target.isRunning &&
            (page.recordCount != target.recordCount ||
                page.traceHeadSha256 != target.traceHeadSha256)) ||
        (anchor != null && record.recordSha256 != anchor)) {
      throw const TraceReadException(TraceReadFailure.integrity);
    }
    if (_bytes + record.byteCount > traceMaxBytes) {
      throw const TraceReadException(TraceReadFailure.limit);
    }
    final caption = AgentCaption.fromRecord(record, _clock());
    if (caption == null) {
      _uncaptioned++;
    } else {
      _captions.add(caption);
    }
    _owner = record.ownerRef;
    _head = record.recordSha256;
    _bytes += record.byteCount;
    _sequence++;
  }

  void close() {
    if (_disposed) return;
    _generation++;
    _active = false;
    _reading = false;
    _following = true;
    if (_cancelled != null && !_cancelled!.isCompleted) _cancelled!.complete();
    _captions.clear();
    _anchors.clear();
    _sequence = 0;
    _bytes = 0;
    _uncaptioned = 0;
    _head = traceGenesis;
    _owner = null;
    _failure = _invalidBinding ? TraceReadFailure.integrity : null;
    notifyListeners();
  }

  @override
  void dispose() {
    close();
    _disposed = true;
    super.dispose();
  }
}
