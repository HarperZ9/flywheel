// The operations the lane console proposes, derived the way the engine
// derives them (harness/gateway_operation.py, lane_settings_route.py): the
// approval sheet compares destination, tool and scopes with the engine's
// proposal, so a client that derived a different value would never approve.
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

GatewayOperation _exact(String action, Map<String, Object?> operation,
        {Set<String> pathKeys = const {}}) =>
    GatewayOperation.exact(
        action: action,
        operation: operation,
        clientRequestId: 'lane-test-1',
        pathKeys: pathKeys);

void main() {
  test('choosing node.exe is a setting with write and exec scopes', () {
    final op =
        _exact('settings.node_path', {'path': r'C:\tools\node\node.exe'});
    expect(op.destination, const GatewayDestination('setting', 'node_path'));
    expect(op.tool, 'settings.node_path');
    expect(op.scopes, ['write', 'exec']);
  });

  test('choosing the local-model folder is a setting with write scope', () {
    final op = _exact('lane.root', {'path': r'D:\projects\site'});
    expect(op.destination,
        const GatewayDestination('setting', 'local-model-root'));
    expect(op.tool, 'lane.root');
    expect(op.scopes, ['write']);
  });

  test('clearing a setting sends no path', () {
    final op = _exact('settings.node_path', const {});
    expect(op.operation.containsKey('path'), isFalse);
    expect(op.scopes, ['write', 'exec']);
  });

  test('a lane call carries a local path only in a declared path argument', () {
    final args = {'thesis': r'C:\work\thesis.md', 'limit': 3};
    final op = _exact('lane.call',
        {'name': 'crucible', 'tool': 'crucible.assess', 'args': args},
        pathKeys: {'thesis'});
    expect(op.destination, const GatewayDestination('lane', 'crucible'));
    expect(op.tool, 'crucible.assess');
    expect(op.scopes, ['exec', 'network', 'plugin']);
    expect(
        () => _exact('lane.call',
            {'name': 'crucible', 'tool': 'crucible.assess', 'args': args}),
        throwsArgumentError);
    expect(
        () => _exact('lane.call', {
              'name': 'crucible',
              'tool': 'crucible.assess',
              'args': {'note': r'C:\work\thesis.md'}
            }, pathKeys: {
              'thesis'
            }),
        throwsArgumentError);
  });

  test('a declared path argument still refuses a secret shape', () {
    expect(
        () => _exact('lane.call', {
              'name': 'gather',
              'tool': 'gather.docs',
              'args': {'path': 'api_key=abcdefghijklmnop'}
            }, pathKeys: {
              'path'
            }),
        throwsArgumentError);
  });
}
