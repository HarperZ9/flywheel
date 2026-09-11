part of 'rowan_operation_controller.dart';

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
  required AgentToolProtocol toolProtocol,
  Map<String, Object?>? continuation,
}) =>
    GatewayOperation.exact(
      action: 'agent.run',
      clientRequestId: requestId,
      operation: {
        'goal': goal,
        'endpoint': endpoint,
        if (model != null && model.isNotEmpty) 'model': model,
        if (toolProtocol.wire != null) 'tool_protocol': toolProtocol.wire,
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
