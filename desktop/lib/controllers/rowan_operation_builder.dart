part of 'rowan_operation_controller.dart';

GatewayOperation _rowanOperation({
  required String requestId,
  required String goal,
  required String endpoint,
  required String? model,
  required String? root,
  required AgentExecutionMode executionMode,
  required EffortLevel effort,
  required int maxSteps,
  required int maxTokens,
  required int timeoutSeconds,
  required bool allowWrite,
  required bool allowExec,
  required AgentToolProtocol toolProtocol,
  Map<String, Object?>? continuation,
}) =>
    agentRunOperation(
      requestId: requestId,
      goal: goal,
      endpoint: endpoint,
      model: model,
      root: root,
      executionMode: executionMode,
      effort: effort,
      maxSteps: maxSteps,
      maxTokens: maxTokens,
      timeoutSeconds: timeoutSeconds,
      allowWrite: allowWrite,
      allowExec: allowExec,
      toolProtocol: toolProtocol,
      continuation: continuation,
    );
