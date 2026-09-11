import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

import 'gateway_agent_execution_review_fixtures.dart';

void main() {
  test('agent execution summary accepts backend review and legacy omission',
      () {
    final parsed = GatewayGrantProposal.fromJson(gatewayAgentProposal());

    expect(parsed.invalidResponse, isFalse);
    expect(parsed.summary.agentExecution?.bindingSha256,
        gatewayExplicitBindingHash);
    expect(parsed.summary.agentExecution?.model.requestedModelReference,
        'operator-model:tag');
    expect(parsed.summary.agentExecution?.model.modelId, 'operator-model:tag');
    expect(parsed.summary.agentExecution?.model.selection, 'explicit');
    expect(parsed.summary.agentExecution?.workspacePolicySha256,
        gatewayWorkspacePolicyHash);
    expect(parsed.summary.agentExecution?.budget.maxSteps, 2);
    expect(parsed.summary.agentExecution?.capabilities.allowExec, isFalse);

    final frozenDefault = GatewayGrantProposal.fromJson(gatewayAgentProposal(
        agentExecution: gatewayDefaultAgentExecutionReview));
    expect(frozenDefault.invalidResponse, isFalse);
    final frozenReview = frozenDefault.summary.agentExecution!;
    expect(frozenReview.bindingSha256, gatewayDefaultBindingHash);
    expect(frozenReview.model.requestedModelReference, isNull);
    expect(frozenReview.model.requestedLabel, 'endpoint default');
    expect(frozenReview.model.modelId, 'telos-coder-14b');
    expect(frozenReview.model.selection, 'frozen_default');
    expect(frozenReview.model.selectionLabel, 'frozen endpoint default');

    final legacy = GatewayGrantProposal.fromJson(
        gatewayAgentProposal(agentExecution: null));
    expect(legacy.invalidResponse, isFalse);
    expect(legacy.summary.agentExecution, isNull);
  });

  test('agent observation policy labels stay pre-run', () {
    const labels = {
      'ollama_exact': 'Ollama exact check during run',
      'provider_reported': 'provider-reported string during run',
      'unavailable': 'unavailable until run',
    };
    for (final entry in labels.entries) {
      final parsed = GatewayGrantProposal.fromJson(gatewayAgentProposal(
        agentExecution: {
          ...gatewayAgentExecutionReview,
          'model': {
            ...gatewayAgentExecutionReview['model'] as Map<String, Object?>,
            'observation_policy': entry.key,
          },
        },
      ));
      expect(parsed.invalidResponse, isFalse);
      expect(parsed.summary.agentExecution?.model.observationPolicyLabel,
          entry.value);
    }
  });

  test('agent execution summary is scoped to agent runs', () {
    final parsed = GatewayGrantProposal.fromJson(gatewayAgentProposal(
      action: 'plugin.invoke',
      tool: 'plugin.invoke',
    ));

    expect(parsed.invalidResponse, isTrue);
  });

  test('agent execution status-only reprepare stays explicit', () {
    final parsed = GatewayGrantProposal.fromJson(gatewayAgentProposal(
        agentExecution: const {'status': 'reprepare_required'}));

    expect(parsed.invalidResponse, isFalse);
    expect(parsed.summary.agentExecution?.reprepareRequired, isTrue);
  });

  test('agent execution summary rejects unknown or malformed fields', () {
    for (final bad in [
      {...gatewayAgentExecutionReview, 'extra': 'field'},
      {
        ...gatewayAgentExecutionReview,
        'tool_protocol': gatewayTextToolProtocol
      },
      {...gatewayAgentExecutionReview, 'binding_sha256': 'short'},
      {
        ...gatewayAgentExecutionReview,
        'model': {
          ...gatewayAgentExecutionReview['model'] as Map<String, Object?>,
          'selection': 'observed',
        },
      },
      {...gatewayAgentExecutionReview, 'base_url': ''},
      {
        ...gatewayAgentExecutionReview,
        'base_url': 'https://example.invalid/v1?token=x',
      },
      {
        ...gatewayAgentExecutionReview,
        'budget': {
          'max_steps': 2,
          'max_tokens': true,
          'timeout_s': 300,
        },
      },
      {...gatewayAgentExecutionReview, 'root': 'relative\\workspace'},
      {...gatewayAgentExecutionReview, 'root': 'FILE:/tmp/workspace'},
      {
        ...gatewayAgentExecutionReview,
        'root': 'https://workspace.invalid/root'
      },
      {...gatewayAgentExecutionReview, 'root': 'password=abcdefghijklmnop'},
    ]) {
      expect(
          GatewayGrantProposal.fromJson(
                  gatewayAgentProposal(agentExecution: bad))
              .invalidResponse,
          isTrue);
    }
  });

  testWidgets('reprepare-required agent review blocks approval',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = await preparedAgentGrantController(
        agentExecution: const {'status': 'reprepare_required'});
    await openGatewayGrantSheet(tester, controller);

    expect(find.textContaining('Status: reprepare required'), findsOneWidget);
    expect(find.text('Prepare again required'), findsOneWidget);
    final approve = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Prepare again required'));
    expect(approve.onPressed, isNull);
  });

  testWidgets('agent grant sheet renders frozen execution authority',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = await preparedAgentGrantController();
    await openGatewayGrantSheet(tester, controller);

    expect(find.text('Agent execution'), findsOneWidget);
    expect(find.textContaining('Requested model: operator-model:tag'),
        findsOneWidget);
    expect(find.textContaining('Resolved model: operator-model:tag'),
        findsOneWidget);
    expect(find.textContaining('Selection: explicit request'), findsOneWidget);
    expect(
        find.textContaining('Observation basis: Ollama exact check during run'),
        findsOneWidget);
    expect(find.textContaining(r'Workspace: C:\fixture\workspace'),
        findsOneWidget);
    expect(find.textContaining('Budget: 2 steps / 1024 output tokens / 300s'),
        findsOneWidget);
    expect(find.textContaining('Gates: write off / exec off / MCP off'),
        findsOneWidget);
    expect(find.textContaining('Credential refs: None'), findsOneWidget);

    await tester.ensureVisible(find.text('Receipts and policy'));
    await tester.tap(find.text('Receipts and policy'));
    await tester.pumpAndSettle();

    expect(find.text('Binding'), findsOneWidget);
    expect(find.text('Workspace policy'), findsOneWidget);
  });
}
