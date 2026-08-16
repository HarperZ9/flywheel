import 'dart:async';

import 'package:flutter/foundation.dart';

import '../client/gateway_client.dart';
import '../controllers/gateway_operation_controller.dart';
import '../models/operation_models.dart';

export '../models/gateway_grant_models.dart' show GatewayJourneyBinding;

enum OperationObserverState { idle, connecting, observing, closed, error }

final class OperationController extends ChangeNotifier {
  final String Function() _requestId;
  final int stopTimeoutMs;
  final VoidCallback? _onTerminal;
  final ValueChanged<OperationResult>? _onTerminalResult;
  final GatewayOperationController? grants;
  OperationSnapshot? _execution;
  OperationResult? _terminalResult;
  GatewayOperation? _pendingStop;
  String? _pendingHead;
  StreamSubscription<GatewayOperationEvent>? _watch;
  OperationObserverState _observer = OperationObserverState.idle;
  bool _terminalNotified = false, _disposed = false;

  OperationController({
    required String Function() requestId,
    this.stopTimeoutMs = 5000,
    VoidCallback? onTerminal,
    ValueChanged<OperationResult>? onTerminalResult,
    this.grants,
  })  : _requestId = requestId,
        _onTerminal = onTerminal,
        _onTerminalResult = onTerminalResult {
    if (stopTimeoutMs < 1 || stopTimeoutMs > 30000) {
      throw ArgumentError('Invalid Stop timeout');
    }
  }

  OperationSnapshot? get execution => _execution;
  OperationResult? get terminalResult => _terminalResult;
  OperationObserverState get observerState => _observer;
  GatewayJourneyBinding? get currentBinding => _execution?.binding;
  bool get hasTerminal => _execution?.isTerminal == true;

  void beginObservation() {
    if (_disposed) return;
    _observer = OperationObserverState.connecting;
    notifyListeners();
  }

  void observe(Stream<GatewayOperationEvent> stream,
      {required ValueChanged<Map<String, dynamic>> onProgress,
      required VoidCallback onInterrupted}) {
    if (_disposed) return;
    _watch?.cancel();
    beginObservation();
    _watch = stream.listen((event) {
      if (event.progress != null) onProgress(event.progress!);
      final snapshot = event.snapshot;
      final accepted = event.result == null
          ? snapshot == null || acceptSnapshot(snapshot)
          : snapshot != null && acceptTerminal(snapshot, event.result!);
      if (!accepted) onInterrupted();
    }, onError: (_) {
      failObservation();
      if (!_disposed && !hasTerminal) onInterrupted();
    }, onDone: () {
      closeObservation();
      if (!_disposed && !hasTerminal) onInterrupted();
    });
  }

  bool acceptSnapshot(OperationSnapshot next) {
    if (_disposed) return false;
    final current = _execution;
    if (current != null && next == current) {
      _observer = OperationObserverState.observing;
      notifyListeners();
      return true;
    }
    if (current != null && !_validAdvance(current, next)) {
      _observer = OperationObserverState.error;
      notifyListeners();
      return false;
    }
    _execution = next;
    _observer = OperationObserverState.observing;
    _pendingStop = null;
    _pendingHead = null;
    grants?.invalidate();
    notifyListeners();
    return true;
  }

  bool acceptTerminal(OperationSnapshot next, OperationResult result) {
    final current = _execution;
    if (_disposed ||
        !next.isTerminal ||
        next.operationRef != result.operationRef ||
        next.state != result.state ||
        next.resultSha256 != result.canonicalSha256 ||
        current != null && next != current && !_validAdvance(current, next)) {
      failObservation();
      return false;
    }
    _terminalResult = result;
    if (!acceptSnapshot(next)) return false;
    if (!_terminalNotified) {
      _terminalNotified = true;
      _onTerminalResult?.call(result);
      _onTerminal?.call();
    }
    return true;
  }

  bool acceptCancelResponse(OperationSnapshot response) {
    final current = _execution;
    return !_disposed &&
        current != null &&
        current.operationRef == response.operationRef &&
        current.journeyRef == response.journeyRef &&
        (response.state == OperationState.cancelRequested ||
            response.isTerminal);
  }

  GatewayOperation? stopOperation() {
    final snapshot = _execution;
    if (_disposed ||
        snapshot == null ||
        snapshot.state != OperationState.running ||
        !snapshot.canCancel) {
      return null;
    }
    if (_pendingStop != null && _pendingHead == snapshot.eventHeadSha256) {
      return _pendingStop;
    }
    _pendingHead = snapshot.eventHeadSha256;
    return _pendingStop = GatewayOperation.cancel(
        _requestId(), snapshot.operationRef, stopTimeoutMs);
  }

  bool isPendingOperation(GatewayOperation operation) {
    final snapshot = _execution;
    return !_disposed &&
        operation == _pendingStop &&
        snapshot?.state == OperationState.running &&
        snapshot?.canCancel == true &&
        snapshot?.eventHeadSha256 == _pendingHead;
  }

  Future<bool> prepareStop(GatewayOperation operation) async {
    final grantController = grants;
    final binding = currentBinding;
    if (grantController == null ||
        binding == null ||
        !isPendingOperation(operation)) {
      return false;
    }
    return grantController.prepare(operation,
        binding: binding,
        currentOperation: () =>
            isPendingOperation(operation) ? operation : null,
        currentBinding: () => currentBinding);
  }

  void closeObservation() {
    if (_disposed) return;
    _observer = OperationObserverState.closed;
    notifyListeners();
  }

  void failObservation() {
    if (_disposed) return;
    _observer = OperationObserverState.error;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _watch?.cancel();
    grants?.invalidate();
    super.dispose();
  }
}

bool _validAdvance(OperationSnapshot current, OperationSnapshot next) =>
    current.operationRef == next.operationRef &&
    current.journeyRef == next.journeyRef &&
    current.eventHeadSha256 != next.eventHeadSha256 &&
    allowsOperationTransition(current.state, next.state);
