import '../widgets/effort_dial.dart';
import 'agent_execution_mode.dart';
import 'agent_tool_protocol.dart';
import 'gateway_grant_models.dart';

GatewayOperation agentRunOperation({
  required String requestId,
  required String goal,
  required String endpoint,
  required String? model,
  required String? root,
  required AgentExecutionMode executionMode,
  required EffortLevel effort,
  required int maxSteps,
  required int? maxTokens,
  required int timeoutSeconds,
  required bool allowWrite,
  required bool allowExec,
  required AgentToolProtocol toolProtocol,
  Map<String, Object?>? attachment,
  Map<String, Object?>? continuation,
}) {
  final input = goal.trim();
  if (input.isEmpty || endpoint.isEmpty) throw ArgumentError('invalid agent');
  if (executionMode.isNativeCli) {
    if (!agentExecutionModeSupportsEndpoint(executionMode, endpoint) ||
        model == null ||
        model.isEmpty ||
        root == null ||
        root.isEmpty) {
      throw ArgumentError('invalid native CLI agent');
    }
    return GatewayOperation.exact(
      action: 'agent.run',
      clientRequestId: requestId,
      operation: {
        'goal': input,
        'endpoint': endpoint,
        'model': model,
        'root': root,
        'execution_mode': executionMode.wire,
        'max_steps': maxSteps,
        'timeout_s': timeoutSeconds,
        'allow_write': allowWrite,
        'allow_exec': false,
        'stream': true,
        if (attachment != null) 'attachment': attachment,
        if (continuation != null) 'continuation': continuation,
      },
    );
  }
  return GatewayOperation.exact(
    action: 'agent.run',
    clientRequestId: requestId,
    operation: {
      'goal': input,
      'endpoint': endpoint,
      if (model != null && model.isNotEmpty) 'model': model,
      if (toolProtocol.wire != null) 'tool_protocol': toolProtocol.wire,
      'effort': effort.wire,
      'max_steps': maxSteps,
      if (maxTokens != null) 'max_tokens': maxTokens,
      'timeout_s': timeoutSeconds,
      'allow_write': allowWrite,
      'allow_exec': allowExec,
      'stream': true,
      if (root != null && root.isNotEmpty) 'root': root,
      if (attachment != null) 'attachment': attachment,
      if (continuation != null) 'continuation': continuation,
    },
  );
}
