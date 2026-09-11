import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_host_adapter.dart';
import 'package:flywheel_desktop/models/rowan_walkthrough_models.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';

void main() {
  test('adapter configures walkthrough budget on shared Rowan controller', () {
    final directory = Directory.systemTemp.createTempSync('rowan-host-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final client = GatewayClient();
    final controller = RowanOperationController(
      client,
      sessionStore: JourneySessionStore(
        file: File('${directory.path}${Platform.pathSeparator}session.json'),
      ),
    );
    final host = RowanOperationHostAdapter(controller);
    addTearDown(host.dispose);
    addTearDown(controller.dispose);
    addTearDown(client.close);

    host.configureScenario(rowanRetryPolicyWalkthroughScenario);

    expect(controller.maxSteps, rowanRetryPolicyWalkthroughScenario.maxSteps);
    expect(controller.maxTokens, rowanRetryPolicyWalkthroughScenario.maxTokens);
    expect(
      controller.timeoutSeconds,
      rowanRetryPolicyWalkthroughScenario.timeoutSeconds,
    );
    expect(controller.allowWrite, isFalse);
    expect(controller.allowExec, isFalse);

    controller.setEffort(controller.effort);
    expect(controller.maxSteps,
        isNot(rowanRetryPolicyWalkthroughScenario.maxSteps));
  });

  test('adapter exposes the same operation session as the controller', () {
    final client = GatewayClient();
    final controller = RowanOperationController(client)
      ..setEndpoint('ollama')
      ..setModel('qwen2.5-coder:14b')
      ..setWorkspaceRoot('/workspace');
    final host = RowanOperationHostAdapter(controller);
    addTearDown(host.dispose);
    addTearDown(controller.dispose);
    addTearDown(client.close);

    expect(host.client, same(client));
    expect(host.endpoint, 'ollama');
    expect(host.selectedModel, 'qwen2.5-coder:14b');
    expect(host.workspaceRoot, '/workspace');
    expect(host.snapshot, isNull);
  });
}
