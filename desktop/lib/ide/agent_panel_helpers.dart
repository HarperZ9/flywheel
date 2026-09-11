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
    return GatewayOperation.exact(
      action: 'agent.run',
      clientRequestId: request,
      operation: {
        'goal': input,
        'endpoint': endpoint,
        if (state._model != null && state._model!.isNotEmpty)
          'model': state._model,
        'effort': state._effort.wire,
        'max_steps': state._effort.maxSteps,
        'allow_write': state._allowWrite,
        'allow_exec': state._allowExec,
        'stream': true,
        if (attachment != null) 'attachment': attachment,
        if (state.widget.continuationHandoff != null)
          'continuation': state.widget.continuationHandoff,
        'root': state.widget.workspaceRoot,
      },
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
