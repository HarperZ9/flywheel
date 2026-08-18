import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/models/journey_models.dart';

const _schema = 'flywheel.evidence-transport-error/v1';
const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposal = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _limit = 1048576;

GatewayJourneyApi _api(Future<http.Response> Function(http.Request) handler,
    {String? Function()? readToken}) {
  http.Client transport = MockClient(handler);
  if (readToken != null) {
    transport = AuthedClient(transport, readToken: readToken);
  }
  return GatewayJourneyApi(GatewayClient(httpClient: transport));
}

Map<String, Object?> _error(String code, {int padding = 0}) => {
      'error': {'message': List.filled(padding, 'x').join(), 'code': code},
      'schema': _schema,
    };

Map<String, Object?> _ack() => {
      'schema': 'flywheel.evidence-journey-mutation-ack/v2',
      'journey_ref': _journey,
      'event_head_sha256': _head,
      'event_sha256': _head,
      'projection_sha256': _head,
      'idempotent_replay': false,
    };

JourneyCreateRequest _create(String goal) => JourneyCreateRequest(
    goal: goal,
    intakeRef: 'intake.json',
    clientRequestId: 'create-1',
    grantRef: _grant);

Map<String, dynamic> _createBody(String goal) => {
      'goal': goal,
      'intake_ref': 'intake.json',
      'client_request_id': 'create-1',
      'grant_ref': _grant,
    };

String _goalAtBytes(int target, {required bool multibyte}) {
  final remaining = target - utf8.encode(jsonEncode(_createBody(''))).length;
  if (!multibyte) return List.filled(remaining, 'a').join();
  return '${List.filled(remaining ~/ 2, 'é').join()}'
      '${remaining.isOdd ? 'a' : ''}';
}

Map<String, dynamic> _depthCommand(int depth) {
  Object value = 'leaf';
  for (var level = 1; level < depth; level++) {
    value = [value];
  }
  return {'payload': value};
}

Map<String, dynamic> _nodeCommand(int nodes) =>
    {'items': List<Object?>.filled(nodes - 2, null)};

Future<JourneyApiException> _failure(Future<void> Function() call) async {
  try {
    await call();
  } on JourneyApiException catch (error) {
    return error;
  }
  fail('expected JourneyApiException');
}

void main() {
  _structuredErrorTests();
  _malformedResponseTests();
  _requestBoundaryTests();
  _structureAndSnapshotTests();
  _authAndLocalRefusalTests();
}

void _structuredErrorTests() {
  test('complete reordered known errors retain code with exact status',
      () async {
    const policies = <String, List<int>>{
      'AUTH_REQUIRED': [401],
      'PERMISSION_REQUIRED': [403],
      'PERMISSION_DENIED': [403],
      'APPROVAL_EXPIRED': [403],
      'JOURNEY_NOT_FOUND': [404],
      'HEAD_CONFLICT': [409],
      'VERSION_MISMATCH': [409],
      'IDEMPOTENCY_MISMATCH': [409],
      'INVALID_TRANSITION': [409, 422],
      'STORE_COMMIT_FAILED': [500],
      'STORE_BUSY': [503],
      'CANCEL_UNAVAILABLE': [409],
    };
    for (final entry in policies.entries) {
      final body = jsonEncode(_error(entry.key, padding: 300));
      for (final status in entry.value) {
        final error = await _failure(
            () => _api((_) async => http.Response(body, status)).list());
        expect(error.failure.code, entry.key);
        expect(error.toString(), isNot(contains(body)));
      }
      final mismatch = await _failure(
          () => _api((_) async => http.Response(body, 418)).list());
      expect(mismatch.failure.code, 'INVALID_RESPONSE');
    }
    final legacy = GatewayException('gateway returned 503');
    expect((legacy.statusCode, legacy.message), (503, 'gateway returned 503'));
  });

  test('exact HTTP 200 error envelope remains intentionally typed', () async {
    var body = jsonEncode(_error('AUTH_REQUIRED'));
    final api = _api((_) async => http.Response(body, 200));
    expect((await _failure(api.list)).failure.code, 'AUTH_REQUIRED');
    for (final malformed in [
      {..._error('AUTH_REQUIRED'), 'extra': 'secret'},
      {
        'schema': _schema,
        'error': {'code': 'AUTH_REQUIRED', 'message': '', 'extra': 'secret'}
      }
    ]) {
      body = jsonEncode(malformed);
      expect((await _failure(api.list)).failure.code, 'INVALID_RESPONSE');
    }
  });
}

void _malformedResponseTests() {
  test('malformed and unsafe failures never become display text', () async {
    final bodies = [
      jsonEncode({
        'schema': 'wrong',
        'error': {'code': 'HEAD_CONFLICT', 'message': r'C:\private\hidden.json'}
      }),
      jsonEncode(_error('UNKNOWN_REMOTE', padding: 300)),
      '<html>file:/private/error password=abcdefghijklmnop</html>'
    ];
    for (final body in bodies) {
      final error = await _failure(
          () => _api((_) async => http.Response(body, 500)).list());
      expect(error.failure.code, 'INVALID_RESPONSE');
      expect(error.toString(), isNot(contains(body)));
    }
  });

  test('malformed success stays local invalid response without truth',
      () async {
    final object = await _api((_) async => http.Response('{}', 200))
        .create(_create('Preserve evidence'));
    expect(object.invalidResponse, isTrue);
    final listError = await _failure(
        () => _api((_) async => http.Response('not-json', 200)).list());
    expect(listError.failure.code, 'INVALID_RESPONSE');
  });
}

void _requestBoundaryTests() {
  test('ASCII and multibyte JSON at exact byte limit are sent', () async {
    var calls = 0;
    final api = _api((request) async {
      calls++;
      expect(request.bodyBytes.length, _limit);
      return http.Response(jsonEncode(_ack()), 200);
    });
    for (final multibyte in [false, true]) {
      final goal = _goalAtBytes(_limit, multibyte: multibyte);
      expect(utf8.encode(jsonEncode(_createBody(goal))).length, _limit);
      expect((await api.create(_create(goal))).invalidResponse, isFalse);
    }
    expect(calls, 2);
  });

  test('JSON above exact byte limit fails before any HTTP call', () async {
    var calls = 0;
    final api = _api((_) async {
      calls++;
      return http.Response('{}', 200);
    });
    for (final multibyte in [false, true]) {
      final goal = _goalAtBytes(_limit + 1, multibyte: multibyte);
      final error = await _failure(() => api.create(_create(goal)));
      expect(error.failure.code, 'INVALID_RESPONSE');
    }
    expect(calls, 0);
  });
}

void _structureAndSnapshotTests() {
  test('JSON depth 16 and node 4096 pass; 17 and 4097 fail', () {
    GrantIntent.append(
        journeyRef: _journey,
        expectedEventHead: _head,
        clientRequestId: 'depth-16',
        command: _depthCommand(16));
    expect(
        () => GrantIntent.append(
            journeyRef: _journey,
            expectedEventHead: _head,
            clientRequestId: 'depth-17',
            command: _depthCommand(17)),
        throwsArgumentError);
    JourneyAppendRequest(
        journeyRef: _journey,
        expectedEventHead: _head,
        clientRequestId: 'nodes-4096',
        grantRef: _grant,
        command: _nodeCommand(4096));
    expect(
        () => JourneyAppendRequest(
            journeyRef: _journey,
            expectedEventHead: _head,
            clientRequestId: 'nodes-4097',
            grantRef: _grant,
            command: _nodeCommand(4097)),
        throwsArgumentError);
  });

  test('append values snapshot nested data and reject non-JSON numbers', () {
    final command = <String, dynamic>{
      'nested': {
        'items': <String>['original']
      }
    };
    final request = JourneyAppendRequest(
        journeyRef: _journey,
        expectedEventHead: _head,
        clientRequestId: 'snapshot',
        grantRef: _grant,
        command: command);
    ((command['nested'] as Map)['items'] as List)[0] = 'changed';
    expect(((request.command['nested'] as Map)['items'] as List).single,
        'original');
    for (final invalid in [double.nan, Object()]) {
      expect(
          () => GrantIntent.append(
              journeyRef: _journey,
              expectedEventHead: _head,
              clientRequestId: 'invalid',
              command: {'value': invalid}),
          throwsArgumentError);
    }
  });
}

void _authAndLocalRefusalTests() {
  test('401 invalidates token and explicit retry succeeds with rotation',
      () async {
    final tokens = ['synthetic-token-a', 'synthetic-token-b'];
    final headers = <String?>[];
    final api = _api((request) async {
      headers.add(request.headers['Authorization']);
      if (headers.length == 1) {
        return http.Response(
            jsonEncode(_error('AUTH_REQUIRED', padding: 300)), 401);
      }
      return http.Response(
          jsonEncode(
              {'schema': 'flywheel.evidence-journey-list/v2', 'journeys': []}),
          200);
    }, readToken: () => tokens.removeAt(0));
    expect((await _failure(api.list)).failure.code, 'AUTH_REQUIRED');
    expect(await api.list(), isEmpty);
    expect(headers, ['Bearer synthetic-token-a', 'Bearer synthetic-token-b']);
  });

  test('invalid local lens refuses before HTTP and approval stays exact',
      () async {
    var calls = 0;
    final api = _api((request) async {
      calls++;
      expect(jsonDecode(request.body), {'proposal_ref': _proposal});
      return http.Response(
          jsonEncode({
            'schema': 'flywheel.operation-grant-approval/v1',
            'grant_ref': _grant,
            'expires_at': '2026-08-15T12:00:00Z'
          }),
          200);
    });
    final error =
        await _failure(() => api.resume(_journey, JourneyLens.invalidResponse));
    expect(error.failure.code, 'INVALID_RESPONSE');
    expect(calls, 0);
    expect((await api.approveGrantOnce(_proposal)).grantRef, _grant);
    expect(calls, 1);
  });
}
