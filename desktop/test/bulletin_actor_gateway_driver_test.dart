import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'support/bulletin_actor_approval.dart';
import 'support/bulletin_actor_exchange.dart';
import 'support/bulletin_actor_launch.dart';
import 'support/bulletin_actor_transport.dart';

// Explicitly launched by the trusted campaign supervisor, never a default test
// that starts a gateway, Worker, model, or external post. Config stays private.
void main() {
  final env = Platform.environment;
  test('one native reviewed synthetic actor operation', () async {
    ActorGatewayTransport? transport;
    try {
      final configFile = File(env['BULLETIN_ACTOR_FIXTURE_CONFIG'] ?? '');
      if (!configFile.uri.isAbsolute ||
          configFile.resolveSymbolicLinksSync().toLowerCase() !=
              configFile.absolute.path.toLowerCase()) {
        actorInvalid();
      }
      if (FileSystemEntity.typeSync(configFile.path, followLinks: false) !=
              FileSystemEntityType.file ||
          configFile.lengthSync() > 65536) {
        actorInvalid();
      }
      final handle = configFile.openSync();
      late List<int> bytes;
      try {
        bytes = handle.readSync(65537);
      } finally {
        handle.closeSync();
      }
      if (bytes.length > 65536) actorInvalid();
      final config = ActorRecord(bytes);
      final launch = ActorLaunch(config.value, config.sha256, env);
      final exchange = ActorExchange(env['BULLETIN_ACTOR_EXCHANGE'] ?? '');
      var event = 0;
      transport = ActorGatewayTransport(
          launch.gatewayOrigin, config.value['token'] as String,
          onEvent: (stage, path) {
        if (event > 11) actorInvalid();
        final index = event++;
        exchange.write(
            'transport-${index.toString().padLeft(2, '0')}.json',
            {
              'schema_version': 1,
              'run_id': launch.runId,
              'slot_id': launch.slotId,
              'stage': stage,
              'path': path,
              'index': index,
            },
            2048);
      });
      final grants = GatewayGrantClient(GatewayClient(
          baseUrl: launch.gatewayOrigin.toString(), httpClient: transport));
      await announceActorReady(grants, exchange);
      stdout.writeln('BULLETIN_ACTOR_READY');
      await stdout.flush();
      // Parent owns the actor's active deadline; this is an absolute idle fence.
      final descriptor = await exchange.wait(
          'descriptor.json', 16384, const Duration(seconds: 240));
      launch.admitDescriptor(descriptor.value);
      transport.restrictTimeout(Duration(
          milliseconds: descriptor.value['request_timeout_ms'] as int));
      final proposal = await exchange.wait(
          'proposal.json', 8192, const Duration(seconds: 5),
          expectedSha: descriptor.value['proposal_sha256'] as String);
      final driver = ActorApprovalDriver(grants, exchange,
          runId: launch.runId,
          slotId: launch.slotId,
          proposalSha: proposal.sha256,
          recordingFailed: () => transport!.recordingFailed,
          reviewWait: Duration(
              milliseconds: descriptor.value['review_wait_max_ms'] as int),
          activeBudget: Duration(
              milliseconds: descriptor.value['remaining_active_ms'] as int));
      await driver
          .run(launch.operation(proposal), launch.binding,
              capabilityChecked: true)
          .timeout(Duration(
              milliseconds: (descriptor.value['remaining_active_ms'] as int) +
                  (descriptor.value['review_wait_max_ms'] as int)));
      if (transport.recordingFailed) actorInvalid();
    } on Object {
      // No raw exception, request text, path, token, response or config dump.
      fail('BULLETIN_ACTOR_DRIVER_INCOMPLETE');
    } finally {
      transport?.close();
    }
  },
      skip: !env.containsKey('BULLETIN_ACTOR_EXCHANGE'),
      timeout: const Timeout(Duration(minutes: 8)));
}
