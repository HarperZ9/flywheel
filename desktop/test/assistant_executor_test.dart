// The assistant executor carries out a plan: a work task starts a witnessed run
// through the gateway, a device action opens its deep link, and every command is
// logged. The gateway agent sink is exercised against a mock http client, so the
// accountable path is verified without a running gateway.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/assistant/assistant_executor.dart';
import 'package:flywheel_desktop/assistant/assistant_intent.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';

class _RecAgent implements AgentSink {
  _RecAgent([this.next = 'run-1']);
  final List<String> tasks = [];
  final String? next;

  @override
  Future<String?> startTask(String goal) async {
    tasks.add(goal);
    return next;
  }
}

class _RecDevice implements DeviceSink {
  final List<String> opened = [];
  bool result = true;

  @override
  Future<bool> open(String deepLink) async {
    opened.add(deepLink);
    return result;
  }
}

void main() {
  test('a work command starts a witnessed run and logs it', () async {
    final agent = _RecAgent('run-42');
    final device = _RecDevice();
    final ex = AssistantExecutor(agent: agent, device: device);

    final rec = await ex.handle('refactor the parser');

    expect(rec.channel, AssistantChannel.agent);
    expect(agent.tasks.single, 'refactor the parser');
    expect(rec.runId, 'run-42');
    expect(rec.ok, isTrue);
    expect(device.opened, isEmpty);
    expect(ex.log, hasLength(1));
  });

  test('a device command opens the deep link and never touches the agent', () async {
    final agent = _RecAgent();
    final device = _RecDevice();
    final ex = AssistantExecutor(agent: agent, device: device);

    final rec = await ex.handle('navigate to the airport');

    expect(rec.channel, AssistantChannel.device);
    expect(device.opened.single, contains('destination=the%20airport'));
    expect(agent.tasks, isEmpty);
    expect(rec.reply, contains('directions to the airport'));
  });

  test('an agent that cannot start is an honest failure', () async {
    final ex = AssistantExecutor(agent: _RecAgent(null), device: _RecDevice());
    final rec = await ex.handle('do the thing');
    expect(rec.ok, isFalse);
    expect(rec.runId, isNull);
  });

  test('the gateway agent sink posts the goal and returns the run_id', () async {
    final client = GatewayClient(
      baseUrl: 'https://pc.example',
      httpClient: MockClient((req) async {
        expect(req.url.path, '/api/relay/start');
        expect(jsonDecode(req.body)['goal'], 'fix the flaky test');
        return http.Response(jsonEncode({'run_id': 'r-9', 'checkpoint': 'abc'}), 200);
      }),
    );
    expect(await GatewayAgentSink(client).startTask('fix the flaky test'), 'r-9');
  });

  test('the gateway agent sink returns null when the gateway errors', () async {
    final client = GatewayClient(
      baseUrl: 'https://pc.example',
      httpClient: MockClient((_) async => http.Response('nope', 500)),
    );
    expect(await GatewayAgentSink(client).startTask('x'), isNull);
  });
}
