part of 'agent_panel.dart';

GatewayOperation? _agentOperation(_AgentPanelState state, String request) {
  final endpoint = state._endpoint;
  final input = state._goal.text.trim();
  if (endpoint == null || input.isEmpty) return null;
  try {
    final attachment = closedEditorAttachment(
      state._attachContext,
      state.widget.currentAttachment,
      state.widget.activeFile,
      state.widget.selection,
    );
    return agentRunOperation(
      requestId: request,
      goal: input,
      endpoint: endpoint,
      model: state._model,
      root: state.widget.workspaceRoot,
      executionMode: state._executionMode,
      effort: state._effort,
      maxSteps: state._executionMode.isNativeCli
          ? state._nativeCliMaxSteps
          : state._effort.maxSteps,
      maxTokens: null,
      timeoutSeconds: 300,
      allowWrite: state._allowWrite,
      allowExec: state._allowExec,
      toolProtocol: state._toolProtocol,
      attachment: attachment,
      continuation: state.widget.continuationHandoff,
    );
  } catch (_) {
    return null;
  }
}

Widget _agentPastSection(_AgentPanelState state) => ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 280),
      child: SingleChildScrollView(
        child: state._stored != null
            ? StoredAgentRun(doc: state._stored!, client: state.widget.client)
            : AgentRunsList(runs: state._pastRuns, onOpen: state._openStored),
      ),
    );

Widget _agentHeader(_AgentPanelState state, FwTokens t) => Row(
      children: [
        Kicker('workspace agent', hot: !state._pastOpen),
        const Spacer(),
        if (!state.widget.alive)
          Text('engine offline', style: fwMono(t, size: 10.5, color: t.drift))
        else
          TextButton(
            onPressed: state._togglePastRuns,
            child: Text(
              state._pastOpen ? 'live' : 'past runs',
              style: fwMono(t, size: 11, color: t.inkMuted),
            ),
          ),
      ],
    );
