import '../models/assistant_task.dart';
import 'gateway_client.dart';

abstract interface class AssistantTaskApi {
  Future<List<AssistantTask>> recent();
  Future<AssistantTask> read(String runId);
}

class GatewayAssistantTaskApi implements AssistantTaskApi {
  GatewayAssistantTaskApi(this.client);
  final GatewayClient client;

  @override
  Future<List<AssistantTask>> recent() async {
    final doc = await client.relayRuns();
    final rows = doc['runs'];
    if (doc.containsKey('error') || rows is! List || rows.length > 64) {
      throw const FormatException('Gateway tasks unavailable');
    }
    final tasks = <AssistantTask>[];
    final refs = <String>{};
    for (final row in rows) {
      final task = AssistantTask.fromStatus(row);
      if (task == null || !refs.add(task.runId)) {
        throw const FormatException('Gateway task response invalid');
      }
      tasks.add(task);
    }
    return List.unmodifiable(tasks);
  }

  @override
  Future<AssistantTask> read(String runId) async {
    if (!isAssistantRunRef(runId)) {
      throw const FormatException('Invalid run reference');
    }
    try {
      final task = AssistantTask.fromStatus(await client.relayStatus(runId),
          expectedRef: runId);
      if (task == null) return AssistantTask.unknown(runId);
      if (task.state != AssistantTaskState.completed) return task;
      try {
        return task.withResult(await client.relayResult(runId));
      } catch (_) {
        return task.resultUnavailable;
      }
    } catch (_) {
      return AssistantTask.unknown(runId);
    }
  }
}
