// The twelve action routes reach the operator through the same grant sheet as
// chat and plugins. The client derives destination, tool, and scopes locally
// so the sheet can name a target before the engine answers; if that
// derivation drifts from harness/gateway_operation_shape.py the sheet asks
// for one thing and the engine grants another. These lock the mirror.

import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/gateway_grant_models.dart';

GatewayOperation _op(String action, Map<String, Object?> operation) =>
    GatewayOperation.exact(
        action: action, clientRequestId: 'request-1', operation: operation);

void main() {
  test('each action route names the destination the engine names', () {
    final cases = <String, (Map<String, Object?>, String, String)>{
      'bench.run': (
        {'tasks': [], 'endpoints': []},
        'bench',
        'private-bench'
      ),
      'capability.probe': ({'endpoint': 'local'}, 'endpoint', 'local'),
      'invent.round': ({'k': 3}, 'forge', 'conjecture-forge'),
      'lean.check': ({'code': 'theorem t : True := trivial'}, 'oracle', 'lean'),
      'suite.audit': ({'path': 'C:/dev/project'}, 'suite', 'C:/dev/project'),
      'lane.call': (
        {'name': 'gather', 'tool': 'gather.status', 'args': {}},
        'lane',
        'gather'
      ),
      'store.put': ({'kind': 'note', 'data': {}}, 'store', 'note'),
      'import.config': ({'root': 'C:/dev/project'}, 'workspace', 'C:/dev/project'),
      'packs.admit': (
        {'manifest': {'pack_id': 'flywheel.finance.claims'}},
        'pack',
        'flywheel.finance.claims'
      ),
      // A scan with no root reads the environment, and the sheet says so
      // rather than naming a directory nobody chose.
      'infra.credential_scan': (const {}, 'scan', 'environment'),
      'infra.isolation': (const {}, 'boundary', 'isolation'),
      'infra.kill': (
        {'reason': 'drill', 'authority_1': 'a', 'authority_2': 'b'},
        'kill-switch',
        'evidence-preserving'
      ),
    };
    cases.forEach((action, expected) {
      final op = _op(action, expected.$1);
      expect(op.destination.kind, expected.$2, reason: action);
      expect(op.destination.ref, expected.$3, reason: action);
    });
  });

  test('scopes match the engine, and a lane call is the widest of them', () {
    expect(_op('bench.run', {'tasks': [], 'endpoints': []}).scopes,
        ['exec', 'network']);
    expect(_op('capability.probe', {'endpoint': 'local'}).scopes, ['network']);
    expect(_op('invent.round', {'k': 1}).scopes, ['write', 'network']);
    expect(_op('lean.check', {'code': 'x'}).scopes, ['write', 'exec']);
    expect(_op('suite.audit', {'path': 'C:/dev/p'}).scopes, ['exec']);
    expect(
        _op('lane.call', {'name': 'g', 'tool': 't', 'args': {}}).scopes,
        ['exec', 'network', 'plugin']);
    expect(_op('store.put', {'kind': 'n', 'data': {}}).scopes, ['write']);
    expect(_op('import.config', {'root': 'C:/dev/p'}).scopes, ['write']);
    expect(
        _op('packs.admit', {'manifest': {'pack_id': 'p'}}).scopes, ['write']);
    expect(_op('infra.credential_scan', const {}).scopes, ['secrets']);
    expect(_op('infra.isolation', const {}).scopes, ['network']);
    expect(
        _op('infra.kill',
            {'reason': 'd', 'authority_1': 'a', 'authority_2': 'b'}).scopes,
        ['exec', 'network', 'secrets']);
  });

  test('a scan names the root it was given, and a kill names its mode', () {
    expect(
        _op('infra.credential_scan', {'root': 'C:/dev/project'})
            .destination.ref,
        'C:/dev/project');
    expect(
        _op('infra.kill', {
          'reason': 'd',
          'authority_1': 'a',
          'authority_2': 'b',
          'mode': 'destructive'
        }).destination.ref,
        'destructive');
  });

  test('a lane call proposes the lane tool, not its own action name', () {
    // The sheet says what will be invoked. Naming the action here would show
    // the operator "lane.call" where the engine records "gather.status".
    expect(_op('lane.call', {'name': 'gather', 'tool': 'gather.status',
        'args': {}}).tool, 'gather.status');
    expect(_op('suite.audit', {'path': 'C:/dev/p'}).tool, 'suite.audit');
  });

  test('an unnamed manifest is said to be unnamed rather than invented', () {
    expect(_op('packs.admit', {'manifest': {}}).destination.ref,
        'unnamed-pack');
    expect(_op('packs.admit', {'manifest': {'name': 'from-name'}})
        .destination.ref, 'from-name');
  });

  test('path fields carry a local path; other fields still may not', () {
    // root, path, and fixtures_root are exempt from the public-text rule
    // because a workspace root is a local path by definition. The exemption
    // is per-field: the same string in another field is refused.
    expect(_op('import.config', {'root': r'C:\dev\project'}).operation['root'],
        r'C:\dev\project');
    expect(
        () => _op('store.put', {'kind': r'C:\dev\project', 'data': {}}),
        throwsA(isA<ArgumentError>()));
  });

  test('a field that reads as a credential is refused before dispatch', () {
    expect(
        () => _op('store.put', {'kind': 'note', 'data': {'api_key': 'sk-1'}}),
        throwsA(isA<ArgumentError>()));
    expect(
        () => _op('lane.call',
            {'name': 'g', 'tool': 't', 'args': {'password': 'hunter2'}}),
        throwsA(isA<ArgumentError>()));
  });

  test('a field the destination is derived from cannot be missing', () {
    expect(() => _op('suite.audit', const {}), throwsA(isA<ArgumentError>()));
    expect(() => _op('import.config', const {}), throwsA(isA<ArgumentError>()));
    expect(() => _op('lane.call', const {'tool': 't', 'args': {}}),
        throwsA(isA<ArgumentError>()));
  });

  test('field-set exactness is decided by the engine, not the client', () {
    // canonicalize_operation in harness/gateway_operation.py refuses an extra
    // field; the client does not restate that table. An extra field therefore
    // builds here and is refused at prepare, before any sheet is shown. The
    // client mirrors only what it must render before the engine answers.
    expect(_op('lean.check', {'code': 'x', 'extra': 1}).operation['extra'], 1);
  });
}
