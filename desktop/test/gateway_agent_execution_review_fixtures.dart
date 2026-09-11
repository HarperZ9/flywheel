import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/gateway_grants.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/operation_grant_sheet.dart';

const gatewayAgentTestHash =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const gatewayExplicitBindingHash =
    '23bf265c3a138fcbc28840431a5cc49a01dd032b4f87f0effe8fefc529670a33';
const gatewayDefaultBindingHash =
    '3b76f5a55e3920324f354bd42c3d61f4997b6f327810663d5a4b6cb835a1a7e8';
const gatewayWorkspacePolicyHash =
    '709271920c84a91aa06ffc9c9689d0334e5284a4cce7924d00887acc0c07f271';
const gatewayAgentTestJourney = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const gatewayAgentTestBinding =
    GatewayJourneyBinding(gatewayAgentTestJourney, gatewayAgentTestHash);

const gatewayAgentExecutionReview = {
  'schema': 'flywheel.gateway-agent-review/v1',
  'binding_sha256': gatewayExplicitBindingHash,
  'endpoint': 'ollama',
  'base_url': 'http://127.0.0.1:11434/v1',
  'model': {
    'requested_model_reference': 'operator-model:tag',
    'model_id': 'operator-model:tag',
    'selection': 'explicit',
    'observation_policy': 'ollama_exact',
    'profile': null,
  },
  'root': r'C:\fixture\workspace',
  'workspace_policy_sha256': gatewayWorkspacePolicyHash,
  'budget': {
    'max_steps': 2,
    'max_tokens': 1024,
    'timeout_s': 300,
  },
  'capabilities': {
    'allow_exec': false,
    'allow_mcp': false,
    'allow_write': false,
  },
};

final gatewayDefaultAgentExecutionReview = {
  ...gatewayAgentExecutionReview,
  'binding_sha256': gatewayDefaultBindingHash,
  'model': const {
    'requested_model_reference': null,
    'model_id': 'telos-coder-14b',
    'selection': 'frozen_default',
    'observation_policy': 'ollama_exact',
    'profile': null,
  },
};

GatewayOperation gatewayAgentRunOperation() => GatewayOperation.exact(
      action: 'agent.run',
      clientRequestId: 'request-1',
      operation: const {
        'goal': 'fixture',
        'endpoint': 'ollama',
        'model': 'operator-model:tag',
        'max_steps': 2,
        'max_tokens': 1024,
        'timeout_s': 300,
        'allow_exec': false,
        'allow_write': false,
        'allow_mcp': false,
        'stream': true,
      },
    );

Map<String, Object?> gatewayAgentProposal({
  Object? agentExecution = gatewayAgentExecutionReview,
  String action = 'agent.run',
  String tool = 'agent.run',
}) {
  const destination = {'kind': 'endpoint', 'ref': 'ollama'};
  final summary = <String, Object?>{
    'schema': 'flywheel.gateway-grant-summary/v1',
    'action': action,
    'journey_ref': gatewayAgentTestJourney,
    'expected_event_head': gatewayAgentTestHash,
    'destination': destination,
    'tool': tool,
    'operation_sha256': gatewayAgentTestHash,
    'arguments_sha256': gatewayAgentTestHash,
    'scopes': ['network'],
    'data_refs': <String>[],
    'credential_refs': <String>[],
    'effect': 'one dispatch after approval',
    'expires_at': '2026-09-10T20:02:00Z',
  };
  if (agentExecution != null) summary['agent_execution'] = agentExecution;
  return {
    'schema': 'flywheel.gateway-grant-proposal/v1',
    'proposal_ref': 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'planned_grant_ref': 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'action': action,
    'journey_ref': gatewayAgentTestJourney,
    'expected_event_head': gatewayAgentTestHash,
    'client_request_id': 'request-1',
    'destination': destination,
    'tool': tool,
    'operation_sha256': gatewayAgentTestHash,
    'arguments_sha256': gatewayAgentTestHash,
    'scopes': ['network'],
    'data_refs': <String>[],
    'credential_refs': <String>[],
    'expires_at': '2026-09-10T20:02:00Z',
    'summary': summary,
  };
}

Future<GatewayOperationController> preparedAgentGrantController({
  Object? agentExecution = gatewayAgentExecutionReview,
}) async {
  final controller = GatewayOperationController(GatewayGrantClient(
      GatewayClient(
          baseUrl: 'https://gateway.invalid',
          httpClient: MockClient((_) async => http.Response(
              jsonEncode(gatewayAgentProposal(agentExecution: agentExecution)),
              200)))));
  final operation = gatewayAgentRunOperation();
  final prepared = await controller.prepare(operation,
      binding: gatewayAgentTestBinding,
      currentOperation: () => operation,
      currentBinding: () => gatewayAgentTestBinding);
  if (!prepared) throw StateError('fixture grant controller did not prepare');
  return controller;
}

Future<void> openGatewayGrantSheet(
  WidgetTester tester,
  GatewayOperationController controller,
) async {
  await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Builder(builder: (context) {
        return FilledButton(
            onPressed: () => showOperationGrantSheet<void>(
                context, controller, (_) async {}),
            child: const Text('Open'));
      })));
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
}
