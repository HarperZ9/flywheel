part of 'provider_session_surface.dart';

extension _ProviderSessionSurfaceActions on _ProviderSessionSurfaceState {
  Future<void> _sendTurn() async {
    final binding = _binding;
    final text = widget.draft.trim();
    if (binding == null ||
        !_bindingIsCurrent(binding) ||
        text.isEmpty ||
        _authorizing) {
      return;
    }
    final state = widget.controller.state;
    final stateKey = _ProviderSessionStateKey.from(state);
    final model = _modelText;
    final requestId = 'native-turn-${DateTime.now().microsecondsSinceEpoch}';
    final operation = _turnOperation(requestId, binding, state, text, model);
    await _authorizeStart(
      operation,
      providerSessionTurnPath,
      currentOperation: () => _bindingIsCurrent(binding) &&
              widget.draft.trim() == text &&
              _modelText == model &&
              stateKey.matches(widget.controller.state)
          ? operation
          : null,
    );
  }

  Future<void> _resume() async {
    final binding = _binding;
    final state = widget.controller.state;
    final stateKey = _ProviderSessionStateKey.from(state);
    final source = state.operationRef;
    if (binding == null ||
        !_bindingIsCurrent(binding) ||
        source.isEmpty ||
        _authorizing) {
      return;
    }
    final requestId = 'native-resume-${DateTime.now().microsecondsSinceEpoch}';
    final operation = ProviderSessionResumeRequest(
      provider: binding.provider,
      workspaceRef: binding.workspaceRef,
      configDigest: binding.configDigest,
      providerBindingRef: binding.providerBindingRef,
      capabilityDigest: _optionalCapability(binding),
      sourceOperationRef: source,
      nativeSessionId: _emptyToNull(state.nativeSessionId),
      nativeThreadId: _emptyToNull(state.nativeThreadId),
      lastProviderEventId: _emptyToNull(state.lastProviderEventId),
      historyLimit: 20,
      timeoutSeconds: 300,
    ).toGatewayOperation(requestId);
    await _authorizeStart(operation, providerSessionResumePath,
        currentOperation: () => _bindingIsCurrent(binding) &&
                stateKey.matches(widget.controller.state)
            ? operation
            : null);
  }

  Future<void> _reconcile() async {
    final binding = _binding;
    final state = widget.controller.state;
    final stateKey = _ProviderSessionStateKey.from(state);
    final target = state.operationRef;
    if (binding == null ||
        !_bindingIsCurrent(binding) ||
        target.isEmpty ||
        _authorizing) {
      return;
    }
    final requestId =
        'native-reconcile-${DateTime.now().microsecondsSinceEpoch}';
    final operation = ProviderSessionReconcileRequest(
      provider: binding.provider,
      workspaceRef: binding.workspaceRef,
      configDigest: binding.configDigest,
      providerBindingRef: binding.providerBindingRef,
      capabilityDigest: _optionalCapability(binding),
      targetOperationRef: target,
      reason: 'desktop_reconcile_before_resend',
      nativeSessionId: _emptyToNull(state.nativeSessionId),
      nativeThreadId: _emptyToNull(state.nativeThreadId),
      lastProviderEventId: _emptyToNull(state.lastProviderEventId),
      historyLimit: 20,
      timeoutSeconds: 300,
    ).toGatewayOperation(requestId);
    await _authorizeStart(operation, providerSessionReconcilePath,
        currentOperation: () => _bindingIsCurrent(binding) &&
                stateKey.matches(widget.controller.state)
            ? operation
            : null);
  }

  Future<void> _authorizeStart(
    GatewayOperation operation,
    String path, {
    required GatewayOperationSupplier currentOperation,
  }) async {
    _update(() {
      _authorizing = true;
      _runError = null;
      _approvalError = null;
    });
    await authorizeGatewayStream(
      context,
      operation,
      (body) {
        if (!mounted) return;
        _resetOperationController();
        _operation.observe(
          _operations.start(body, path: path),
          onProgress: widget.controller.acceptProgress,
          onInterrupted: () => _update(() => _runError = 'watch_interrupted'),
          onSnapshot: (snapshot) {
            _bindSnapshot(snapshot);
            _startApprovalPoll(snapshot.operationRef);
          },
        );
      },
      () {
        _update(() => _runError = 'approval_denied_or_missing');
      },
      currentOperation: currentOperation,
    );
    _update(() => _authorizing = false);
  }

  Future<void> _stop() async {
    final operation = _operation.stopOperation();
    if (operation == null || !await _operation.prepareStop(operation)) return;
    if (!mounted) return;
    await showOperationGrantSheet<OperationSnapshot>(
      context,
      _stopGrants,
      (body) async {
        final snapshot = await _operations.cancel(body);
        if (!_operation.acceptCancelResponse(snapshot)) {
          throw StateError('invalid operation response');
        }
        return snapshot;
      },
    );
  }

  void _bindSnapshot(OperationSnapshot snapshot) {
    if (widget.controller.state.operationRef != snapshot.operationRef) {
      widget.controller.begin(snapshot.operationRef);
    }
    if (snapshot.isTerminal) _stopApprovalPoll(clear: false);
  }

  GatewayOperation _turnOperation(String requestId, ProviderSessionBinding b,
      ProviderSessionState state, String text, String? model) {
    return ProviderSessionTurnRequest(
      provider: b.provider,
      workspaceRef: b.workspaceRef,
      configDigest: b.configDigest,
      providerBindingRef: b.providerBindingRef,
      capabilityDigest: _optionalCapability(b),
      model: model,
      permissionScope: _permissionScope,
      input: [
        {'type': 'input_text', 'text': text}
      ],
      resumePolicy: state.nativeThreadId.isEmpty
          ? ProviderSessionResumePolicy.newThread
          : ProviderSessionResumePolicy.resumeAfterReconcile,
      nativeSessionId: _emptyToNull(state.nativeSessionId),
      nativeThreadId: _emptyToNull(state.nativeThreadId),
      nativeTurnId: _emptyToNull(state.nativeTurnId),
      sourceOperationRef: _emptyToNull(state.operationRef),
      timeoutSeconds: 300,
    ).toGatewayOperation(requestId);
  }

  Future<void> _readPendingApproval(String operationRef) async {
    try {
      final approvals =
          await widget.client.providerSessionApprovals(operationRef);
      if (!mounted || widget.controller.state.operationRef != operationRef) {
        return;
      }
      _update(() {
        _pendingApproval =
            approvals.pending.isEmpty ? null : approvals.pending.first;
        _approvalError = null;
      });
    } on Object catch (error) {
      if (!mounted || widget.controller.state.operationRef != operationRef) {
        return;
      }
      _update(() => _approvalError = _bindingMessage(error));
    }
  }

  void _startApprovalPoll(String operationRef) {
    _approvalPoll?.cancel();
    unawaited(_readPendingApproval(operationRef));
    _approvalPoll = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted ||
          widget.controller.state.operationRef != operationRef ||
          widget.controller.state.terminal) {
        _stopApprovalPoll(clear: false);
        return;
      }
      unawaited(_readPendingApproval(operationRef));
    });
  }

  void _stopApprovalPoll({required bool clear}) {
    _approvalPoll?.cancel();
    _approvalPoll = null;
    if (clear && mounted) _update(() => _pendingApproval = null);
  }

  Future<void> _allowPendingApproval() =>
      _respondPendingApproval('allow', const {'decision': 'accept'});

  Future<void> _denyPendingApproval() => _respondPendingApproval('deny', null);

  Future<void> _respondPendingApproval(
      String decision, Map<String, Object?>? updatedInput) async {
    final approval = _pendingApproval;
    final operationRef = widget.controller.state.operationRef;
    if (approval == null ||
        _authorizing ||
        operationRef.isEmpty ||
        approval.operationRef != operationRef) {
      return;
    }
    final requestId =
        'native-approval-${DateTime.now().microsecondsSinceEpoch}';
    final operation = ProviderSessionApprovalResponseRequest(
      operationRef: approval.operationRef,
      nativeRequestId: approval.nativeRequestId,
      requestIdentity: approval.requestIdentity,
      decision: decision,
      clientResponseId: requestId,
      updatedInput: updatedInput,
    ).toGatewayOperation(requestId);
    _update(() {
      _authorizing = true;
      _approvalError = null;
    });
    final outcome =
        await authorizeGatewayOperationDetailed<Map<String, dynamic>>(
      context,
      operation,
      (body) async => widget.client.respondProviderSessionApproval(body),
      currentOperation: () {
        final current = _pendingApproval;
        return current != null &&
                current.operationRef == operationRef &&
                current.requestIdentity == approval.requestIdentity &&
                widget.controller.state.operationRef == operationRef
            ? operation
            : null;
      },
    );
    if (!mounted) return;
    _update(() {
      _authorizing = false;
      if (outcome.failure != null) {
        _approvalError = outcome.failure!.code;
      } else if (outcome.denied) {
        _approvalError = 'approval_denied_or_missing';
      } else {
        _pendingApproval = null;
      }
    });
    if (widget.controller.state.operationRef.isNotEmpty) {
      unawaited(_readPendingApproval(widget.controller.state.operationRef));
    }
  }
}

String? _emptyToNull(String value) => value.isEmpty ? null : value;
String? _optionalCapability(ProviderSessionBinding binding) =>
    binding.capabilityDigest.isEmpty ? null : binding.capabilityDigest;
