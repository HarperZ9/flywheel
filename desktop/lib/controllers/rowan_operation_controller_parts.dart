part of 'rowan_operation_controller.dart';

extension RowanOperationControllerLifecycle on RowanOperationController {
  Future<GatewayAuthorizationOutcome<bool>> start(
    BuildContext context,
    String goal, {
    Map<String, Object?>? continuation,
  }) async {
    if (_recoveryBlocked) {
      _error = 'OPERATION_RECOVERY_PENDING';
      _changed();
      return GatewayAuthorizationOutcome.failure(
        const GatewayOperationFailure(
          'OPERATION_RECOVERY_PENDING',
          'A pending operation could not be recovered yet',
        ),
      );
    }
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
    if (_executionMode.isNativeCli &&
        !agentExecutionModeSupportsEndpoint(_executionMode, endpoint)) {
      _error = 'AGENT_CLI_PROFILE_UNSUPPORTED';
      _changed();
      return GatewayAuthorizationOutcome.failure(
        const GatewayOperationFailure(
          'AGENT_CLI_PROFILE_UNSUPPORTED',
          'Codex CLI native sessions are unavailable',
        ),
      );
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
        executionMode: _executionMode,
        effort: _effort,
        maxSteps: maxSteps,
        maxTokens: _maxTokens,
        timeoutSeconds: _timeoutSeconds,
        allowWrite: _allowWrite,
        allowExec: _allowExec,
        toolProtocol: _toolProtocol,
        continuation: continuation,
      );
    } on Object {
      _error = 'INVALID_CONTEXT';
      _changed();
      return const GatewayAuthorizationOutcome.denied();
    }

    _authorizing = true;
    _error = null;
    _changed();

    try {
      final outcome = await authorizeGatewayOperationDetailed<bool>(
        context,
        operation,
        (body) async {
          _pendingRequestSha256 = requestHash;
          _saveRowanSessionLocator(
            store: _sessionStore,
            requestSha256: requestHash,
            pendingRequestSha256: _pendingRequestSha256,
            operationExecutionMode: _executionMode.wire,
          );
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

  Future<bool> reconnect(OperationSnapshot hint) async {
    _error = null;
    _changed();
    try {
      final fresh = await _operations.snapshot(hint.operationRef);
      if (fresh.journeyRef != hint.journeyRef) {
        throw StateError('operation journey changed');
      }
      if (fresh.isTerminal) {
        final result = await _operations.result(fresh.operationRef);
        if (!_operationState.acceptTerminal(fresh, result)) {
          throw StateError('operation state rejected');
        }
      } else {
        final accepted = _operationState.acceptRecoveredSnapshot(
          fresh,
          _operationState.lastSequence,
        );
        if (!accepted) throw StateError('operation state rejected');
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
        operationExecutionMode: _executionMode.wire,
      );
      _recoveryBlocked = false;
      _changed();
      return true;
    } catch (error) {
      _error = '$error';
      _changed();
      return false;
    }
  }

  Future<bool> recoverFromSession() async {
    final session = _sessionStore?.load();
    if (session == null) return false;
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

void _blockRowanRecovery(RowanOperationController owner, String requestSha) {
  owner._pendingRequestSha256 = requestSha;
  owner._recoveryBlocked = true;
  owner._error = 'OPERATION_RECOVERY_PENDING';
  owner._changed();
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
      operationExecutionMode: owner._executionMode.wire,
    );
  }
  owner._progress = List<Map<String, dynamic>>.unmodifiable([
    ...owner._progress,
    {...result.result, 'type': 'done'},
  ]);
  owner._changed();
}
