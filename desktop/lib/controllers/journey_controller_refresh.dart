part of 'journey_controller.dart';

int _autoWorkspaceDraftSeq = 0;

extension JourneyControllerRefresh on JourneyController {
  /// Only reads are replayed, after any queued mutation has settled.
  Future<void> retryRead() => _readRetry ??= _q(() async {
    if (_disposed) return;
    if (_view.ref == null || _view.projection == null) {
      await initialize();
    } else {
      await refreshActiveProjection();
    }
  }).whenComplete(() => _readRetry = null);

  Future<void> selectJourney(String ref) => _select(ref, _view.lens, false);

  Future<void> selectLens(JourneyLens lens) =>
      _view.projection == null || lens == JourneyLens.invalidResponse
          ? Future.sync(() => _view.remote(_invalid()))
          : _select(_view.ref!, lens, true);

  Future<void> refreshActiveProjection() {
    final ref = _view.ref;
    return ref == null ? Future.value() : _select(ref, _view.lens, false);
  }

  /// Select an existing Journey or create a default workspace Journey so
  /// coding sessions do not dead-end on JOURNEY_REQUIRED.
  Future<bool> ensureWorkspaceJourney({
    String goal = 'Workspace coding session',
    String intakeRef = 'workspace-default',
  }) async {
    if (_disposed) return false;
    if (_hasValidActiveProjection()) return true;
    if (_view.journeys.isEmpty && _view.phase == JourneyViewPhase.idle) {
      await initialize();
      if (_disposed) return false;
      if (_hasValidActiveProjection()) return true;
    }
    for (final item in _view.journeys) {
      if (!item.invalidResponse && item.journeyRef.isNotEmpty) {
        await openSession(item.journeyRef, _view.lens);
        if (_hasValidActiveProjection()) return true;
        break;
      }
    }
    final micros = DateTime.now().microsecondsSinceEpoch;
    final seq = ++_autoWorkspaceDraftSeq;
    final hex = '${micros.toRadixString(16).padLeft(24, '0')}'
        '${seq.toRadixString(16).padLeft(8, '0')}';
    final draft = JourneyDraft(
      draftRef: 'dft_${hex.substring(hex.length - 32)}',
      journeyRef: null,
      baseEventHeadSha256: null,
      kind: 'create',
      payload: {
        'client_request_id': 'workspace-journey-$micros-$seq',
        'goal': goal.trim().isEmpty ? 'Workspace coding session' : goal.trim(),
        'intake_ref':
            intakeRef.trim().isEmpty ? 'workspace-default' : intakeRef.trim(),
      },
      state: JourneyDraftState.dirty,
      updatedAt: DateTime.now().toUtc(),
    );
    await submitStart(draft);
    return _hasValidActiveProjection();
  }

  bool _hasValidActiveProjection() {
    final active = _view.projection;
    return active != null &&
        !active.invalidResponse &&
        _view.ref == active.journeyRef;
  }
}
