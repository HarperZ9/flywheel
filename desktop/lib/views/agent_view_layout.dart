part of 'agent_view.dart';

extension _AgentViewLayout on _AgentViewState {
  void _scrollToEnd() => _workspace.scrollToLatestIfFollowing();

  void _conversationChanged() {
    _refresh(() {});
    _admission.persistHistory();
  }

  void _showConversations() => showChatConversationSheet(context,
      conversations: _conversations,
      current: _current,
      streaming: _busy,
      onNew: _newChat,
      onSelect: _select,
      onDelete: _delete);

  void _useWorkspaceGoal(String goal) {
    _admission.changeDraft(_current, goal);
    _refresh(() {
      _agentSeedGoal = goal;
      _agentMode = true;
      _nativeSessionMode = false;
    });
  }

  void _openModels() => FlywheelNav.jump(context, DestinationId.models);

  Widget _header({bool showConversations = false}) => ChatHeader(
      agentMode: _agentMode,
      nativeSessionMode: _nativeSessionMode,
      streaming: _busy,
      endpoints: _endpoints,
      endpoint: _model,
      chosenModel: _nativeSessionMode
          ? _nativeModels[_nativeSessionKey()]
          : _chosenModels[_model],
      onMode: (v) => _refresh(() {
            _agentMode = v;
            _nativeSessionMode = false;
            if (!v) _agentSeedGoal = null;
          }),
      onNativeSession: () => _refresh(() {
            _agentMode = false;
            _nativeSessionMode = true;
            _agentSeedGoal = null;
          }),
      onEndpoint: (v) => _refresh(() {
            _model = v;
            _current.model = v;
          }),
      onModel: (v) => _refresh(() {
            if (_nativeSessionMode) {
              final key = _nativeSessionKey();
              v.isEmpty ? _nativeModels.remove(key) : _nativeModels[key] = v;
              return;
            }
            v.isEmpty
                ? _chosenModels.remove(_model)
                : _chosenModels[_model!] = v;
          }),
      onShowConversations: showConversations ? _showConversations : null,
      loadModels: () => widget.client.models(_model ?? ''));

  Widget _body() {
    if (_nativeSessionMode) return _nativeSessionSurface();
    return _agentMode
        ? AgentModePane(
            client: widget.client,
            alive: widget.alive,
            settings: widget.settings,
            initialGoal: _agentSeedGoal)
        : _current.isEmpty
            ? ChatWelcome(
                child: StartTaskPrelude(
                    endpoints: _endpoints,
                    endpoint: _model,
                    chosenModel: _chosenModels[_model],
                    streaming: _busy,
                    initialText: _admission.draftText(_current),
                    onDraftChanged: _draftChanged,
                    onSend: _send,
                    onEndpoint: (v) => _refresh(() {
                          _model = v;
                          _current.model = v;
                        }),
                    onModel: (v) => _refresh(() => v.isEmpty
                        ? _chosenModels.remove(_model)
                        : _chosenModels[_model!] = v),
                    loadModels: () => widget.client.models(_model ?? ''),
                    onOpenModels: _openModels,
                    onUseWorkspaceGoal: _useWorkspaceGoal))
            : ChatWorkspace(
                key: ValueKey(_current.id),
                conversation: _current,
                controller: _workspace,
                onConversationChanged: _conversationChanged,
                actionCueController: widget.actionCueController,
              );
  }

  Widget _nativeSessionSurface() {
    final key = _nativeSessionKey();
    return ProviderSessionSurface(
        key: ValueKey(key),
        client: widget.client,
        controller: _nativeSession,
        provider: _nativeProvider,
        draft: _nativeDrafts[key] ?? '',
        workspaceRef: _nativeWorkspaceRef,
        selectedModel: _nativeSelectedModel,
        onProviderChanged: (value) => _refresh(() {
              final currentDraft = _nativeDrafts[key];
              _nativeProvider = value;
              if (currentDraft != null) {
                _nativeDrafts[_nativeSessionKey()] = currentDraft;
              }
            }),
        onDraftChanged: (text) =>
            _refresh(() => _nativeDrafts[_nativeSessionKey()] = text));
  }

  String _nativeSessionKey() {
    final journey =
        GatewayOperationScope.maybeOf(context)?.journey?.state.activeJourneyRef;
    return '${journey ?? _current.id}:$_nativeProvider';
  }

  String? get _nativeSelectedModel {
    final chosen = _nativeModels[_nativeSessionKey()];
    return chosen == null || chosen.isEmpty ? null : chosen;
  }

  String? get _nativeWorkspaceRef {
    final root = widget.settings.recentWorkspaces.isEmpty
        ? null
        : widget.settings.recentWorkspaces.first;
    if (root == null || root.isEmpty) return null;
    return workspaceReference(root);
  }

  Widget _composer() => ChatComposer(
      key: ValueKey(_current.id),
      streaming: _streaming,
      initialText: _admission.draftText(_current),
      onDraftChanged: _draftChanged,
      onSend: _send,
      savedPrompts: widget.settings.savedPrompts,
      onSavePrompt: (text) => _refresh(() => widget.settings.savePrompt(text)));
}

bool _validEvent(Map<String, dynamic> event) => switch (event) {
      {'type': 'delta', 'content': final String value} => value.isNotEmpty,
      {'type': 'done', 'receipt': final Map<String, dynamic> _} => true,
      _ => false,
    };
