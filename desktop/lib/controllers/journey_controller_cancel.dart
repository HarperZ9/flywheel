part of 'journey_controller.dart';

/// The cancellation command flow, held in its own part as an extension so the
/// controller file stays under the size guideline. This follows the same
/// extension-over-`part` pattern the refresh and support parts already use;
/// library-private members (`_view`, `_grant`, `_acks`, ...) stay in reach.
extension JourneyControllerCancel on JourneyController {
  Future<void> _cancel(String operation) async {
    final current = _view.projection;
    if (current == null || !operationRefPattern.hasMatch(operation)) {
      _view.remote(_invalid());
      return;
    }
    final target = _capture();
    _view.busy(JourneyViewPhase.cancelling, operation: operation);
    _view.cancelResult = null;
    final key = '${current.journeyRef}:$operation';
    final head = _cancelHeads.putIfAbsent(key, () => current.eventHeadSha256);
    try {
      final request = 'cancel:$operation';
      final granted = await _grant(
          GrantIntent.cancel(
              journeyRef: current.journeyRef,
              expectedEventHead: head,
              clientRequestId: request,
              operationRef: operation),
          'cancel');
      final result = await _api.cancel(JourneyCancelRequest(
          journeyRef: current.journeyRef,
          expectedEventHead: head,
          clientRequestId: request,
          grantRef: granted.$1,
          operationRef: operation));
      _accept(_terminal(result, operation));
      final token = _acks.add(current.journeyRef, result.eventHeadSha256);
      _cancelHeads.remove(key);
      if (_view.ref == current.journeyRef) _view.cancelResult = result;
      await _refreshAck(token, target.lens);
    } on Object catch (error) {
      final failure = _fail(error);
      if (failure.code == 'HEAD_CONFLICT') {
        await _conflict(failure, target, operation: operation);
      } else if (_current(target)) {
        _view.remote(failure);
      }
    }
  }
}
