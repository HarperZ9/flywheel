import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/agent_execution_mode.dart';
import 'package:flywheel_desktop/models/agent_run_operation.dart';
import 'package:flywheel_desktop/models/agent_tool_protocol.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/widgets/effort_dial.dart';

const Object _absent = Object();

GatewayOperation _op(String action, Map<String, Object?> operation) =>
    GatewayOperation.exact(
      action: action,
      clientRequestId: 'request-1',
      operation: operation,
    );

Map<String, Object?> _agent({Object? protocol = _absent}) => {
      'goal': 'fixture',
      'endpoint': 'openai',
      'max_steps': 2,
      'allow_write': false,
      'allow_exec': false,
      'stream': true,
      if (protocol != _absent) 'tool_protocol': protocol,
    };

const _mcpReceipt =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

const _mcpAdmission = {
  'schema': 'flywheel.agent-run-mcp-admission-request/v1',
  'servers': [
    {
      'server_id': 'synthetic',
      'catalog_ref': 'synthetic',
      'receipt_sha256': _mcpReceipt,
      'tools': ['echo'],
      'timeout_s': 5,
    },
  ],
};

const _callerAuthoredMcpAdmission = {
  'schema': 'flywheel.agent-run-mcp-admission-request/v1',
  'servers': [
    {
      'server_id': 'synthetic',
      'catalog_ref': 'synthetic',
      'receipt_sha256': _mcpReceipt,
      'tools': ['echo'],
      'timeout_s': 5,
      'discovery': {
        'mode': 'cached',
        'server_info': {'name': 'synthetic', 'version': '1.0.0'},
        'protocol_version': '2025-06-18',
        'tools': <Object>[],
      },
      'authority': {
        'echo': {
          'read': true,
          'write': false,
          'execute': false,
          'critical': false,
          'network': false,
        },
      },
    },
  ],
};

void main() {
  test('agent tool protocol is bounded to the backend grammar', () {
    expect(_op('agent.run', _agent()).operation.containsKey('tool_protocol'),
        isFalse);
    expect(
        _op('agent.run', _agent(protocol: 'native')).operation['tool_protocol'],
        'native');
    expect(
        _op('agent.run', _agent(protocol: 'text')).operation['tool_protocol'],
        'text');
    expect(() => _op('agent.run', _agent(protocol: 'json')),
        throwsA(isA<ArgumentError>()));
    expect(() => _op('agent.run', _agent(protocol: 1)),
        throwsA(isA<ArgumentError>()));
    expect(
      () => _op('chat.complete', {
        'model': 'gpt-6-astra',
        'messages': const [
          {'role': 'user', 'content': 'hi'},
        ],
        'stream': true,
        'tool_protocol': 'native',
      }),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('agent MCP admission only accepts backend receipt selections', () {
    expect(
        _op('agent.run', {..._agent(), 'mcp_admission': _mcpAdmission})
            .operation['mcp_admission'],
        _mcpAdmission);
    expect(
      () => _op('agent.run', {
        ..._agent(),
        'mcp_admission': _callerAuthoredMcpAdmission,
      }),
      throwsA(isA<ArgumentError>()),
    );
    expect(
      () => _op('agent.run', {
        ..._agent(),
        'mcp_admission': {
          'schema': 'flywheel.agent-run-mcp-admission-request/v1',
          'servers': [
            {
              'server_id': 'synthetic',
              'catalog_ref': 'synthetic',
              'receipt_sha256': _mcpReceipt,
              'tools': ['echo'],
              'timeout_s': 5,
              'credential_refs': ['cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],
            },
          ],
        },
      }),
      throwsA(isA<ArgumentError>()),
    );
  });

  test('agent MCP admission is scoped and blocked for native CLI', () {
    final op = agentRunOperation(
      requestId: 'request-1',
      goal: 'fixture',
      endpoint: 'openai',
      model: 'gpt-6-astra',
      root: r'C:\fixture\workspace',
      executionMode: AgentExecutionMode.api,
      effort: EffortLevel.low,
      maxSteps: 1,
      maxTokens: 1024,
      timeoutSeconds: 60,
      allowWrite: false,
      allowExec: false,
      toolProtocol: AgentToolProtocol.native,
      mcpAdmission: _mcpAdmission,
    );

    expect(op.operation['mcp_admission'], _mcpAdmission);
    expect(op.scopes, contains('mcp'));
    expect(
        () => agentRunOperation(
              requestId: 'request-1',
              goal: 'fixture',
              endpoint: 'claude-cli',
              model: 'sonnet',
              root: r'C:\fixture\workspace',
              executionMode: AgentExecutionMode.nativeCliSession,
              effort: EffortLevel.low,
              maxSteps: 1,
              maxTokens: null,
              timeoutSeconds: 60,
              allowWrite: false,
              allowExec: false,
              toolProtocol: AgentToolProtocol.compatibility,
              mcpAdmission: _mcpAdmission,
            ),
        throwsA(isA<ArgumentError>()));
    expect(
        () => _op('agent.run', {
              ..._agent(),
              'execution_mode': 'native_cli_session',
              'mcp_admission': _mcpAdmission,
            }),
        throwsA(isA<ArgumentError>()));
  });
}
