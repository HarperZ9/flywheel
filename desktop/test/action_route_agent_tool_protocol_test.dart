import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

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
}
