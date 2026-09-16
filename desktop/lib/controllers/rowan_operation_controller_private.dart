part of 'rowan_operation_controller.dart';

Map<String, Object?> _jsonObjectCopy(Map<String, Object?> value) {
  final decoded = jsonDecode(jsonEncode(value));
  return _deepJsonObject(decoded);
}

Map<String, Object?> _deepJsonObject(Object? value) {
  if (value is! Map) throw ArgumentError('invalid JSON object');
  final copy = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) throw ArgumentError('invalid JSON object');
    copy[key] = _deepJsonValue(entry.value);
  }
  return Map<String, Object?>.unmodifiable(copy);
}

Object? _deepJsonValue(Object? value) {
  if (value == null || value is String || value is num || value is bool) {
    return value;
  }
  if (value is List) {
    return List<Object?>.unmodifiable(value.map(_deepJsonValue));
  }
  if (value is Map) return _deepJsonObject(value);
  throw ArgumentError('invalid JSON value');
}

extension RowanOperationControllerRecovery on RowanOperationController {
  Future<bool> recoverFromSession() {
    final pending = _recoveryFuture;
    if (pending != null) return pending;
    if (active) return Future<bool>.value(false);
    final session = _sessionStore?.load();
    if (session == null) return Future<bool>.value(false);
    _recovering = true;
    _changed();
    late final Future<bool> recovery;
    recovery = _recoverFromSession(session).whenComplete(() {
      if (identical(_recoveryFuture, recovery)) {
        _recoveryFuture = null;
        _recovering = false;
        _changed();
      }
    });
    _recoveryFuture = recovery;
    return recovery;
  }

  Future<bool> _recoverFromSession(JourneySession session) async {
    final direct = session.operationRef;
    final requestSha = session.operationRequestSha256;
    _executionMode =
        AgentExecutionMode.fromWire(session.operationExecutionMode);
    try {
      if (direct != null) {
        final snapshot = await _operations.snapshot(direct);
        if (snapshot.journeyRef == session.journeyRef) {
          final recovered = await reconnect(snapshot);
          if (!recovered && requestSha != null) {
            _blockRowanRecovery(this, requestSha);
          }
          return recovered;
        }
        if (requestSha == null) return false;
      }
      if (requestSha == null) return false;
      _pendingRequestSha256 = requestSha;
      String? cursor;
      for (var pageIndex = 0; pageIndex < 10; pageIndex++) {
        final page = await _operations.listByJourney(
          session.journeyRef,
          limit: 50,
          cursor: cursor,
        );
        for (final snapshot in page.operations) {
          if (page.requestSha256ByOperation[snapshot.operationRef] ==
              requestSha) {
            final recovered = await reconnect(snapshot);
            if (!recovered) _blockRowanRecovery(this, requestSha);
            return recovered;
          }
        }
        cursor = page.nextCursor;
        if (cursor == null) break;
      }
      _blockRowanRecovery(this, requestSha);
      return false;
    } catch (_) {
      if (requestSha != null) _blockRowanRecovery(this, requestSha);
      return false;
    }
  }
}
