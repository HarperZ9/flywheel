import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_auth.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/models/journey_models.dart';

const _journey = 'jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _head =
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _proposal = 'prp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

GatewayJourneyApi _api(http.Response response) => GatewayJourneyApi(
    GatewayClient(httpClient: MockClient((_) async => response)));

GatewayJourneyApi _handlerApi(
    Future<http.Response> Function(http.Request) handler,
    {String? Function()? readToken}) {
  http.Client transport = MockClient(handler);
  if (readToken != null) {
    transport = AuthedClient(transport, readToken: readToken);
  }
  return GatewayJourneyApi(GatewayClient(httpClient: transport));
}

Map<String, Object?> _proposalJson() => {
      'schema': 'flywheel.grant-proposal/v1',
      'proposal_ref': _proposal,
      'planned_grant_ref': _grant,
      'action': 'append',
      'operation_sha256': _head,
      'expires_at': '2026-08-15T12:00:00Z',
    };

Map<String, Object?> _ackJson() => {
      'schema': 'flywheel.evidence-journey-mutation-ack/v2',
      'journey_ref': _journey,
      'event_head_sha256': _head,
      'event_sha256': _head,
      'projection_sha256': _head,
      'idempotent_replay': false,
    };

Future<JourneyApiException> _failure(Future<void> Function() call) async {
  try {
    await call();
  } on JourneyApiException catch (error) {
    return error;
  }
  fail('expected JourneyApiException');
}

JourneyCreateRequest _createRequest() => JourneyCreateRequest(
    goal: 'Preserve evidence',
    intakeRef: 'intake.json',
    clientRequestId: 'create-1',
    grantRef: _grant);

void main() {
  _fixedErrorTests();
  _malformedSuccessTests();
  _unsafeErrorTests();
  _approvalAndBearerTests();
  _snapshotTests();
}

void _fixedErrorTests() {
  test('known transport failures become typed fixed public failures', () async {
    const expected = {
      'HEAD_CONFLICT': 'Journey state changed',
      'AUTH_REQUIRED': 'Journey authorization is required',
      'VERSION_MISMATCH': 'Journey data version is unavailable',
      'STORE_COMMIT_FAILED': 'Journey persistence failed',
    };
    for (final entry in expected.entries) {
      final body = jsonEncode({
        'schema': 'flywheel.evidence-transport-error/v1',
        'error': {'code': entry.key, 'message': 'server text must not echo'}
      });
      final error = await _failure(() => _api(http.Response(body, 409)).list());
      expect(error.failure.code, entry.key);
      expect(error.failure.detail, entry.value);
      expect(error.failure.invalidResponse, isFalse);
      expect(error.toString(), isNot(contains('server text must not echo')));
    }
  });

  test('an error envelope returned with 200 is still a typed failure',
      () async {
    final error = await _failure(() => _api(http.Response(
            jsonEncode({
              'schema': 'flywheel.evidence-transport-error/v1',
              'error': {'code': 'AUTH_REQUIRED', 'message': 'do not echo this'}
            }),
            200))
        .list());
    expect(error.failure.code, 'AUTH_REQUIRED');
    expect(error.toString(), isNot(contains('do not echo this')));
  });
}

void _malformedSuccessTests() {
  test('malformed object success returns a local invalid-response model',
      () async {
    final result =
        await _api(http.Response('{}', 200)).create(_createRequest());
    expect(result.invalidResponse, isTrue);
    expect(result.journeyRef, isEmpty);
  });

  test('malformed list envelope fails closed instead of returning empty truth',
      () async {
    final error = await _failure(() => _api(http.Response('{}', 200)).list());
    expect(error.failure.code, 'INVALID_RESPONSE');
    expect(error.failure.detail, 'Gateway response was invalid');
  });

  test('non-JSON success becomes a fixed local invalid response', () async {
    final error = await _failure(
        () => _api(http.Response('not-json-response', 200)).list());
    expect(error.failure.code, 'INVALID_RESPONSE');
    expect(error.toString(), isNot(contains('not-json-response')));
  });
}

void _unsafeErrorTests() {
  test('unknown or unsafe error bodies never enter displayable failures',
      () async {
    final bodies = [
      jsonEncode({
        'schema': 'wrong',
        'error': {'code': 'HEAD_CONFLICT', 'message': r'C:\private\hidden.json'}
      }),
      jsonEncode({
        'schema': 'flywheel.evidence-transport-error/v1',
        'error': {
          'code': 'UNKNOWN_REMOTE',
          'message': 'password=abcdefghijklmnop'
        }
      }),
      '<html>file:/private/error</html>',
    ];
    for (final body in bodies) {
      final error = await _failure(() =>
          _api(http.Response(body, 500)).resume(_journey, JourneyLens.rescue));
      expect(error.failure.code, 'INVALID_RESPONSE');
      expect(error.failure.detail, 'Gateway response was invalid');
      expect(error.toString(), isNot(contains(body)));
      expect(error.toString(), isNot(contains('private')));
      expect(error.toString(), isNot(contains('password')));
    }
  });

  test('malformed typed mutation success stays invalid without inferred truth',
      () async {
    final result = await _api(http.Response(
            jsonEncode({
              'schema': 'flywheel.evidence-journey-mutation-ack/v2',
              'journey_ref': _journey,
              'event_head_sha256': _head,
              'event_sha256': _head,
              'projection_sha256': _head,
              'idempotent_replay': 'yes',
            }),
            200))
        .create(_createRequest());
    expect(result.invalidResponse, isTrue);
    expect(result.idempotentReplay, isFalse);
  });
}

void _approvalAndBearerTests() {
  test('once-only approval sends only the proposal reference', () async {
    final api = _handlerApi((request) async {
      expect(request.url.path, '/api/grants/approve-once');
      expect(jsonDecode(request.body), {'proposal_ref': _proposal});
      return http.Response(
          jsonEncode({
            'schema': 'flywheel.operation-grant-approval/v1',
            'grant_ref': _grant,
            'expires_at': '2026-08-15T12:00:00Z',
          }),
          200);
    });
    expect((await api.approveGrantOnce(_proposal)).grantRef, _grant);
  });

  test('reuses the supplied bearer-aware GatewayClient', () async {
    String? authorization;
    final api = _handlerApi((request) async {
      authorization = request.headers['Authorization'];
      return http.Response(
          jsonEncode(
              {'schema': 'flywheel.evidence-journey-list/v2', 'journeys': []}),
          200);
    }, readToken: () => 'synthetic-test-token');
    await api.list();
    expect(authorization, 'Bearer synthetic-test-token');
  });
}

void _snapshotTests() {
  test('append intent and request snapshot nested JSON before caller mutation',
      () async {
    final intentCommand = <String, dynamic>{
      'type': 'record_claim',
      'claim': {
        'claim_id': 'claim-1',
        'statement': 'Original statement',
        'depends_on': <String>['fact-1'],
        'does_not_prove': 'claim correctness',
      }
    };
    final requestCommand = <String, dynamic>{
      'type': 'record_next_action',
      'next_action': {
        'action_id': 'action-1',
        'kind': 'inspect',
        'description': 'Original action',
        'basis_refs': <String>['claim-1']
      }
    };
    final intent = GrantIntent.append(
        journeyRef: _journey,
        expectedEventHead: _head,
        clientRequestId: 'append-intent',
        command: intentCommand);
    final request = JourneyAppendRequest(
        journeyRef: _journey,
        expectedEventHead: _head,
        clientRequestId: 'append-request',
        grantRef: _grant,
        command: requestCommand);
    (intentCommand['claim'] as Map)['statement'] = 'Changed';
    ((intentCommand['claim'] as Map)['depends_on'] as List).add('fact-2');
    (requestCommand['next_action'] as Map)['description'] = 'Changed';
    final bodies = <Map<String, dynamic>>[];
    final api = _handlerApi((request) async {
      bodies.add(jsonDecode(request.body) as Map<String, dynamic>);
      return http.Response(
          jsonEncode(request.url.path.contains('/grants/')
              ? _proposalJson()
              : _ackJson()),
          200);
    });
    await api.prepareGrant(intent);
    await api.append(request);
    expect((bodies[0]['command'] as Map)['claim'], {
      'claim_id': 'claim-1',
      'statement': 'Original statement',
      'depends_on': ['fact-1'],
      'does_not_prove': 'claim correctness'
    });
    expect((bodies[1]['command'] as Map)['next_action'], {
      'action_id': 'action-1',
      'kind': 'inspect',
      'description': 'Original action',
      'basis_refs': ['claim-1']
    });
  });

  test('append JSON snapshot rejects unsupported and non-finite values', () {
    for (final invalid in [double.nan, Object()]) {
      expect(
          () => JourneyAppendRequest(
              journeyRef: _journey,
              expectedEventHead: _head,
              clientRequestId: 'append-invalid',
              grantRef: _grant,
              command: {'type': 'record_claim', 'claim': invalid}),
          throwsArgumentError);
    }
  });
}
