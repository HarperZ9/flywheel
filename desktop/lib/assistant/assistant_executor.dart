// assistant_executor.dart -- carry out an AssistantPlan and witness what happened.
//
// handle() routes and plans a command, then dispatches it: a work task starts a
// witnessed relay run through the gateway (the accountable path), and a device
// action opens its deep link (music, navigation, a media or timer action). Every
// command it carries out is appended to a log, so what the assistant did is
// auditable, in keeping with the rest of the ecosystem. The two targets are
// interfaces, so the executor is fully testable with recording doubles; the real
// device target launches the link on the phone, which is the part that needs a
// device.

import '../client/gateway_client.dart';
import 'assistant_intent.dart';
import 'assistant_router.dart';

/// Opens a device deep link (a maps or music URL, a media or timer action).
abstract interface class DeviceSink {
  Future<bool> open(String deepLink);
}

/// Starts a witnessed run for a work task and returns its run_id, or null when it
/// could not start.
abstract interface class AgentSink {
  Future<String?> startTask(String goal);
}

/// A witnessed record of one carried-out command.
class AssistantRecord {
  const AssistantRecord({
    required this.command,
    required this.channel,
    required this.reply,
    required this.ok,
    this.deepLink,
    this.runId,
  });

  final String command;
  final AssistantChannel channel;
  final String reply;
  final bool ok;
  final String? deepLink;
  final String? runId;
}

/// Routes, plans, carries out, and witnesses one command at a time.
class AssistantExecutor {
  AssistantExecutor({
    required this.agent,
    required this.device,
    AssistantLinks links = const AssistantLinks(),
  }) : _links = links;

  final AgentSink agent;
  final DeviceSink device;
  final AssistantLinks _links;

  /// What the assistant has carried out, newest last. A small, auditable trail.
  final List<AssistantRecord> log = [];

  Future<AssistantRecord> handle(String command) async {
    final plan = planFor(routeIntent(command), links: _links);
    String? runId;
    var ok = true;
    if (plan.channel == AssistantChannel.agent) {
      runId = await agent.startTask(plan.taskGoal ?? command);
      ok = runId != null;
    } else if (plan.deepLink != null) {
      ok = await device.open(plan.deepLink!);
    }
    final record = AssistantRecord(
      command: command,
      channel: plan.channel,
      reply: plan.spokenReply,
      ok: ok,
      deepLink: plan.deepLink,
      runId: runId,
    );
    log.add(record);
    return record;
  }
}

/// The accountable agent target: post a work task to the gateway's relay route so
/// the run is witnessed and its receipts travel. Testable with a mock http client.
class GatewayAgentSink implements AgentSink {
  GatewayAgentSink(this._client);

  final GatewayClient _client;

  @override
  Future<String?> startTask(String goal) async {
    try {
      final res = await _client.startRelayRun({'goal': goal});
      final runId = res['run_id'];
      return runId is String ? runId : null;
    } catch (_) {
      return null; // an unreachable gateway is an honest failure, not a crash
    }
  }
}
