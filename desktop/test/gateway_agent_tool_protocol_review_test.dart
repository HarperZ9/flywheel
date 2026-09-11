import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

import 'gateway_agent_execution_review_fixtures.dart';

void main() {
  test('agent execution summary accepts v2 native and text tool protocols', () {
    final native = GatewayGrantProposal.fromJson(gatewayAgentProposal(
        agentExecution: gatewayNativeAgentExecutionReview));

    expect(native.invalidResponse, isFalse);
    final nativeReview = native.summary.agentExecution!;
    expect(nativeReview.bindingSha256, gatewayNativeBindingHash);
    expect(nativeReview.model.modelId, 'gpt-6-astra');
    expect(nativeReview.toolProtocol?.protocol, 'native');
    expect(
        nativeReview.toolProtocol?.protocolLabel, 'native / openai_responses');
    expect(nativeReview.toolProtocol?.toolSchemaSha256,
        gatewayNativeToolSchemaHash);
    expect(nativeReview.toolProtocol?.toolNames,
        const ['read_file', 'list_dir', 'grep']);
    expect(nativeReview.toolProtocol?.strictSchemas, isTrue);
    expect(nativeReview.toolProtocol?.parallelToolCalls, isFalse);
    expect(nativeReview.toolProtocol?.resultOrderPolicy,
        'provider_order_sequential');

    final text = GatewayGrantProposal.fromJson(
        gatewayAgentProposal(agentExecution: gatewayTextAgentExecutionReview));
    expect(text.invalidResponse, isFalse);
    final textProtocol = text.summary.agentExecution!.toolProtocol!;
    expect(textProtocol.protocol, 'text');
    expect(textProtocol.protocolLabel, 'text tool loop');
    expect(textProtocol.toolSchemaSha256, isNull);
    expect(textProtocol.toolSchemaDigestLabel, 'none');
  });

  test('agent v2 native tool names must match capability gates', () {
    const writeAndRunNames = [
      'read_file',
      'list_dir',
      'grep',
      'write_file',
      'edit_file',
      'apply_patch',
      'run',
    ];
    final writeAndRunProtocol = {
      ...gatewayOpenAiNativeToolProtocol,
      'tool_names': writeAndRunNames,
    };
    final writeAndRunCapabilities = {
      ...gatewayNativeAgentExecutionReview['capabilities']
          as Map<String, Object?>,
      'allow_exec': true,
      'allow_write': true,
    };

    expect(
        GatewayGrantProposal.fromJson(gatewayAgentProposal(agentExecution: {
          ...gatewayNativeAgentExecutionReview,
          'tool_protocol': writeAndRunProtocol,
        })).invalidResponse,
        isTrue);

    expect(
        GatewayGrantProposal.fromJson(gatewayAgentProposal(agentExecution: {
          ...gatewayNativeAgentExecutionReview,
          'capabilities': writeAndRunCapabilities,
          'tool_protocol': writeAndRunProtocol,
        })).invalidResponse,
        isFalse);

    expect(
        GatewayGrantProposal.fromJson(gatewayAgentProposal(agentExecution: {
          ...gatewayNativeAgentExecutionReview,
          'capabilities': writeAndRunCapabilities,
          'tool_protocol': gatewayOpenAiNativeToolProtocol,
        })).invalidResponse,
        isTrue);
  });

  test('agent v2 protocol review rejects malformed nested authority', () {
    Map<String, Object?> without(Map<String, Object?> source, String key) =>
        Map<String, Object?>.from(source)..remove(key);

    for (final bad in <Map<String, Object?>>[
      without(gatewayNativeAgentExecutionReview, 'tool_protocol'),
      {
        ...gatewayNativeAgentExecutionReview,
        'schema': 'flywheel.gateway-agent-review/v1',
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'extra': 'field',
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'schema': 'flywheel.gateway-agent-tool-protocol/v2',
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'protocol': 'json',
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'native_api_route': null,
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'native_api_route': 'gemini_tool_calls',
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'tool_schema_sha256': 'short',
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'tool_names': ['grep', 'read_file'],
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'strict_schemas': false,
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'parallel_tool_calls': true,
        },
      },
      {
        ...gatewayNativeAgentExecutionReview,
        'tool_protocol': {
          ...gatewayOpenAiNativeToolProtocol,
          'result_order_policy': 'unordered',
        },
      },
      {
        ...gatewayTextAgentExecutionReview,
        'tool_protocol': {
          ...gatewayTextToolProtocol,
          'native_api_route': 'openai_responses',
        },
      },
      {
        ...gatewayTextAgentExecutionReview,
        'tool_protocol': {
          ...gatewayTextToolProtocol,
          'tool_schema_sha256': gatewayNativeToolSchemaHash,
        },
      },
      {
        ...gatewayTextAgentExecutionReview,
        'tool_protocol': {
          ...gatewayTextToolProtocol,
          'tool_names': ['read_file'],
        },
      },
      {
        ...gatewayTextAgentExecutionReview,
        'tool_protocol': {
          ...gatewayTextToolProtocol,
          'strict_schemas': true,
        },
      },
    ]) {
      expect(
          GatewayGrantProposal.fromJson(
                  gatewayAgentProposal(agentExecution: bad))
              .invalidResponse,
          isTrue);
    }
  });

  testWidgets('agent grant sheet renders v2 tool protocol authority',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = await preparedAgentGrantController(
        agentExecution: gatewayNativeAgentExecutionReview);
    await openGatewayGrantSheet(tester, controller);

    expect(find.textContaining('Resolved model: gpt-6-astra'), findsOneWidget);
    expect(find.textContaining('Tool protocol: native / openai_responses'),
        findsOneWidget);
    expect(
        find.textContaining('Tool schema digest: $gatewayNativeToolSchemaHash'),
        findsOneWidget);

    await tester.ensureVisible(find.text('Receipts and policy'));
    await tester.tap(find.text('Receipts and policy'));
    await tester.pumpAndSettle();

    expect(find.text('Tool names'), findsOneWidget);
    expect(find.textContaining('read_file, list_dir, grep'), findsOneWidget);
  });
}
