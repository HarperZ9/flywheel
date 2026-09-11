part of 'rowan_operation_controller.dart';

extension RowanOperationControllerLifecycle on RowanOperationController {
  Future<GatewayAuthorizationOutcome<bool>> start(
    BuildContext context,
    String goal, {
    Map<String, Object?>? continuation,
  }) async {
    if (_authorizing || active) {
      return GatewayAuthorizationOutcome.failure(
        const GatewayOperationFailure(
          'OPERATION_ACTIVE',
          'An operation is already being prepared or observed',
        ),
      );
    }
    final endpoint = _endpoint;
    if (endpoint == null || goal.trim().isEmpty) {
      _error = 'INVALID_CONTEXT';
      _changed();
      return const GatewayAuthorizationOutcome.denied();
    }
    final requestId = 'rowan-agent-${DateTime.now().microsecondsSinceEpoch}';
    final requestHash = rowanRequestIdSha256(requestId);
    final generation = _configGeneration;
    late final GatewayOperation operation;
    try {
      operation = _rowanOperation(
        requestId: requestId,
        goal: goal.trim(),
        endpoint: endpoint,
        model: _selectedModel,
        root: _workspaceRoot,
        effort: _effort,
        maxSteps: maxSteps,
        maxTokens: _maxTokens,
        timeoutSeconds: _timeoutSeconds,
        allowWrite: _allowWrite,
        allowExec: _allowExec,
        continuation: continuation,
      );
    } on Object {
      _error = 'INVALID_CONTEXT';
      _changed();
      return const GatewayAuthorizationOutcome.denied();
    }

    _authorizing = true;
    _error = null;
    _pendingRequestSha256 = requestHash;
    _saveRowanSessionLocator(
      store: _sessionStore,
      requestSha256: requestHash,
      pendingRequestSha256: _pendingRequestSha256,
    );
    _changed();

    try {
      final outcome = await authorizeGatewayOperationDetailed<bool>(
        context,
        operation,
        (body) async {
          _beginRowanRun(this);
          _operationState.observe(
            _operations.start(body),
            onProgress: (event) => _onRowanProgress(this, event),
            onInterrupted: () => _interruptRowan(this),
          );
          return true;
        },
        currentOperation: () =>
            generation == _configGeneration ? operation : null,
      );
      if (outcome.value == true) return outcome;
      _authorizing = false;
      _error = outcome.failure?.code ?? (outcome.denied ? 'DENIED' : 'DENIED');
      _changed();
      return outcome;
    } on Object catch (error) {
      _authorizing = false;
      _error = '$error';
      _changed();
      return GatewayAuthorizationOutcome.failure(
        GatewayOperationFailure('AUTHORIZATION_FAILED', '$error'),
      );
    }
  }

  Future<void> reconnect(OperationSnapshot hint) async {
    _error = null;
    _changed();
    try {
      final fresh = await _operations.snapshot(hint.operationRef);
      if (fresh.journeyRef != hint.journeyRef) {
        throw StateError('operation journey changed');
      }
      if (fresh.isTerminal) {
        final result = await _operations.result(fresh.operationRef);
        _operationState.acceptTerminal(fresh, result);
      } else {
        _operationState.acceptRecoveredSnapshot(
          fresh,
          _operationState.lastSequence,
        );
        _operationState.observe(
          _operations.watch(
            fresh.operationRef,
            afterSequence: _operationState.lastSequence,
          ),
          onProgress: (event) => _onRowanProgress(this, event),
          onInterrupted: () => _interruptRowan(this),
        );
      }
      _saveRowanSessionLocator(
        store: _sessionStore,
        snapshot: fresh,
        pendingRequestSha256: _pendingRequestSha256,
      );
    } catch (error) {
      _error = '$error';
      _changed();
    }
  }

  Future<bool> recoverFromSession() async {
    final session = _sessionStore?.load();
    if (session == null) return false;
    final direct = session.operationRef;
    if (direct != null) {
      final snapshot = await _operations.snapshot(direct);
      if (snapshot.journeyRef != session.journeyRef) return false;
      await reconnect(snapshot);
      return true;
    }
    final requestSha = session.operationRequestSha256;
    if (requestSha == null) return false;
    final page = await _operations.listByJourney(session.journeyRef);
    for (final snapshot in page.operations) {
      if (page.requestSha256ByOperation[snapshot.operationRef] == requestSha) {
        await reconnect(snapshot);
        return true;
      }
    }
    return false;
  }

  Future<OperationListPage> discoverJourney(String journeyRef) =>
      _operations.listByJourney(journeyRef);

  Future<void> stop(BuildContext context) async {
    final operation = _operationState.stopOperation();
    if (operation == null || !await _operationState.prepareStop(operation)) {
      _error = _stopGrants.failure?.code ?? 'STOP_UNAVAILABLE';
      _changed();
      return;
    }
    if (!context.mounted) return;
    await showOperationGrantSheet<OperationSnapshot>(context, _stopGrants, (
      body,
    ) async {
      final snapshot = await _operations.cancel(body);
      if (!_operationState.acceptCancelResponse(snapshot)) {
        throw StateError('invalid operation response');
      }
      return snapshot;
    });
  }
}

OperationController _newRowanOperationState(RowanOperationController owner) =>
    OperationController(
      requestId: () => 'rowan-stop-${DateTime.now().microsecondsSinceEpoch}',
      grants: owner._stopGrants,
      onTerminalResult: (result) => _finishRowanOperation(owner, result),
    )..addListener(owner._changed);

void _beginRowanRun(RowanOperationController owner) {
  owner._operationState.dispose();
  owner._operationState = _newRowanOperationState(owner);
  owner._progress = const [];
  owner._error = null;
  owner._authorizing = false;
  owner._changed();
}

void _onRowanProgress(
  RowanOperationController owner,
  Map<String, dynamic> event,
) {
  owner._progress = List<Map<String, dynamic>>.unmodifiable([
    ...owner._progress,
    event,
  ]);
  owner._changed();
}

void _interruptRowan(RowanOperationController owner) {
  owner._error = 'OBSERVATION_INTERRUPTED';
  owner._changed();
}

void _finishRowanOperation(
  RowanOperationController owner,
  OperationResult result,
) {
  final snapshot = owner._operationState.execution;
  if (snapshot != null) {
    _saveRowanSessionLocator(
      store: owner._sessionStore,
      snapshot: snapshot,
      pendingRequestSha256: owner._pendingRequestSha256,
    );
  }
  owner._progress = List<Map<String, dynamic>>.unmodifiable([
    ...owner._progress,
    {...result.result, 'type': 'done'},
  ]);
  owner._changed();
}

GatewayOperation _rowanOperation({
  required String requestId,
  required String goal,
  required String endpoint,
  required String? model,
  required String? root,
  required EffortLevel effort,
  required int maxSteps,
  required int maxTokens,
  required int timeoutSeconds,
  required bool allowWrite,
  required bool allowExec,
  Map<String, Object?>? continuation,
}) =>
    GatewayOperation.exact(
      action: 'agent.run',
      clientRequestId: requestId,
      operation: {
        'goal': goal,
        'endpoint': endpoint,
        if (model != null && model.isNotEmpty) 'model': model,
        'effort': effort.wire,
        'max_steps': maxSteps,
        'max_tokens': maxTokens,
        'timeout_s': timeoutSeconds,
        'allow_write': allowWrite,
        'allow_exec': allowExec,
        'stream': true,
        if (root != null && root.isNotEmpty) 'root': root,
        if (continuation != null) 'continuation': continuation,
      },
    );

void _saveRowanSessionLocator({
  required JourneySessionStore? store,
  OperationSnapshot? snapshot,
  String? requestSha256,
  String? pendingRequestSha256,
}) {
  if (store == null) return;
  try {
    final prior = store.load();
    final journeyRef = snapshot?.journeyRef ?? prior?.journeyRef;
    if (journeyRef == null) return;
    final startingNewOperation = snapshot == null && requestSha256 != null;
    store.save(
      JourneySession(
        journeyRef: journeyRef,
        lens: prior?.lens ?? JourneyLens.verify,
        selectionRef: prior?.selectionRef,
        operationRef: startingNewOperation
            ? null
            : snapshot?.operationRef ?? prior?.operationRef,
        operationEventHeadSha256: startingNewOperation
            ? null
            : snapshot?.eventHeadSha256 ?? prior?.operationEventHeadSha256,
        operationRequestSha256: requestSha256 ??
            pendingRequestSha256 ??
            prior?.operationRequestSha256,
        detailsExpanded: prior?.detailsExpanded ?? false,
        recoveryVisible: prior?.recoveryVisible ?? false,
      ),
    );
  } on Object {
    // Session locators are hints; authoritative operation state is remote.
  }
}

String rowanRequestIdSha256(String clientRequestId) =>
    sha256.convert(utf8.encode(jsonEncode(clientRequestId))).toString();
