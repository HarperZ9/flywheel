part of 'agent_view.dart';

extension _AgentViewAdmission on _AgentViewState {
  Future<void> _beginAdmission(ChatDraft submitted) async {
    final generation = ++_generation;
    _submittedDraft = submitted;
    _assistant = null;
    _accepted = false;
    _providerDispatchStarted = false;
    _admitting = true;
    _disposition = Completer<PromptDisposition>();
    _contextStatus[submitted.conversationRef] = ChatContextOutcome.pending();
    _refresh(() {});

    final endpoint = _model!;
    final chosen = _chosenModels[endpoint];
    final model = chosen == null ? endpoint : '$endpoint:$chosen';
    final contextResult = await ChatContextController(widget.client).prepare(
        draft: submitted, isCurrent: () => _canStillDispatch(generation));
    if (!_canStillDispatch(generation) || contextResult.cancelled) {
      _retainBeforeProviderDispatch(generation);
      return;
    }
    _contextStatus[submitted.conversationRef] = contextResult;
    if (mounted) _refresh(() {});

    final wire = _providerWire(submitted, contextResult.providerContext);
    final operation = GatewayOperation.chat(submitted.attemptRef!, model, wire,
        dataRefs: const [], credentialRefs: const []);
    if (!mounted) {
      _retainBeforeProviderDispatch(generation);
      return;
    }
    await authorizeGatewayStream(context, operation, (body) {
      if (!_canStillDispatch(generation)) {
        _retainBeforeProviderDispatch(generation);
        return;
      }
      _providerDispatchStarted = true;
      _sub = widget.client.chatStream(wire, model, authorizedBody: body).listen(
          (event) => _onEvent(generation, event),
          onError: (_) => _onObservationClosed(generation),
          onDone: () => _onObservationClosed(generation));
    }, () => _onObservationClosed(generation),
        currentOperation: () => _model == endpoint &&
                _chosenModels[endpoint] == chosen &&
                _admission.draftText(_current) == submitted.text
            ? operation
            : null);
  }

  List<Map<String, String>> _providerWire(
      ChatDraft submitted, String? contextText) {
    final wire = [
      for (final message in _current.messages) message.toWire(),
    ];
    if (contextText != null && contextText.trim().isNotEmpty) {
      wire.add({'role': 'user', 'content': contextText});
    }
    wire.add({'role': 'user', 'content': submitted.text});
    return wire;
  }

  bool _canStillDispatch(int generation) =>
      mounted && generation == _generation && !_providerDispatchStarted;

  void _retainBeforeProviderDispatch(int generation) {
    if (_providerDispatchStarted) return;
    final submitted = _submittedDraft;
    if (submitted != null) _admission.retain(submitted);
    if (mounted && generation == _generation) {
      _finishDisposition(PromptDisposition.retained);
    } else if (!(_disposition?.isCompleted ?? true)) {
      _disposition!.complete(PromptDisposition.retained);
    }
  }

  void _onEvent(int generation, Map<String, dynamic> event) {
    if (!mounted || generation != _generation || !_validEvent(event)) return;
    if (_assistant == null) {
      _acceptFirstEvent(event);
    } else if (_accepted) {
      _applyEvent(_assistant!, event);
    }
    if (_accepted) _scrollToEnd();
  }

  void _acceptFirstEvent(Map<String, dynamic> event) {
    final assistant = ChatMessage(
        role: 'assistant',
        streaming: true,
        attemptRef: _submittedDraft!.attemptRef);
    _applyEvent(assistant, event);
    final decision =
        _admission.acceptFirst(_current, _submittedDraft!, assistant);
    _accepted = decision.visible;
    _assistant = assistant;
    _streaming = decision.visible;
    _finishDisposition(decision.disposition);
  }

  void _applyEvent(ChatMessage assistant, Map<String, dynamic> event) {
    if (event['type'] == 'delta') {
      assistant.text += event['content'] as String;
    } else {
      assistant.setReceipt(event['receipt'] as Map<String, dynamic>?);
    }
  }

  void _onObservationClosed(int generation) {
    if (!mounted || generation != _generation) return;
    if (_assistant == null) {
      _admission.retain(_submittedDraft!);
      _finishDisposition(PromptDisposition.retained);
      return;
    }
    if (!_accepted) return;
    _refresh(() {
      _assistant!.streaming = false;
      if (_assistant!.receipt == null) {
        const unknown = 'Reply interrupted; completion is unknown.';
        _assistant!.text = _assistant!.text.isEmpty
            ? unknown
            : '${_assistant!.text}\n\n$unknown';
      }
      _streaming = false;
    });
    _admission.persistHistory();
  }

  void _finishDisposition(PromptDisposition result) {
    _admitting = false;
    if (!(_disposition?.isCompleted ?? true)) _disposition!.complete(result);
    if (mounted) _refresh(() {});
  }
}
