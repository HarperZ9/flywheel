part of 'rowan_operation_controller.dart';

extension RowanOperationControllerCheck on RowanOperationController {
  /// A check command runs only with exec allowed, and native CLI sessions
  /// run their own tools, so the engine's check applies to neither.
  bool get _checkCommandApplies => _allowExec && !_executionMode.isNativeCli;

  /// The command the engine runs when the model says it is done. Its pass
  /// is what lets the final answer read as verified instead of claimed. It
  /// is not part of an MCP admission, so typing it keeps the admission.
  void setCheckCommand(String value) {
    final next = value.trim().isEmpty ? null : value.trim();
    if (_checkCommand == next) return;
    _checkCommand = next;
    _bump(invalidateMcpAdmission: false);
  }

  /// The owner's per-run limits. The engine fills unset ones with defaults.
  ///
  /// A value out of range is held as invalid, not dropped: the last valid
  /// budget stays, and start() refuses until the field is fixed. The budget
  /// is not part of an MCP admission, so changing it keeps the admission.
  void setRunBudget(RowanRunBudget value) {
    _invalidRunBudget = value.invalidField;
    if (_invalidRunBudget != null) {
      _error = 'INVALID_RUN_BUDGET';
      _changed();
      return;
    }
    if (_runBudget == value) {
      if (_error == 'INVALID_RUN_BUDGET') _bump(invalidateMcpAdmission: false);
      return;
    }
    _runBudget = value;
    _bump(invalidateMcpAdmission: false);
  }
}

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
    if (_invalidRunBudget != null) {
      // The field shows a value the engine would refuse. Sending the last
      // valid budget instead would run under limits the owner did not set.
      _error = 'INVALID_RUN_BUDGET';
      _changed();
      return GatewayAuthorizationOutcome.failure(
        const GatewayOperationFailure(
          'INVALID_RUN_BUDGET',
          'A run budget field holds a value outside its range',
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
        mcpAdmission: _mcpAdmission,
        continuation: continuation,
        runBudget: _runBudget.toWire(),
        testCmd: _checkCommandApplies ? _checkCommand : null,
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
