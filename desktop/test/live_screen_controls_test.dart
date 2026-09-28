import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';

void main() {
  final grant = 'gnt_${'a' * 32}';
  Map<String, dynamic> request(String action) => {
        'schema': gatewayOperationSchema,
        'grant_ref': grant,
        'control': action,
        'session_id': 'session-1',
      };
  Map<String, dynamic> response(String state) => {
        'session_id': 'session-1',
        'state': state,
        'authority': {'action': 'live_screen.control', 'grant_ref': grant},
      };

  test('control uses approved body and exact session path', () async {
    final client = GatewayClient(httpClient: MockClient((call) async {
      expect(call.url.path, '/api/live-screen/sessions/session-1/stop');
      expect(call.followRedirects, isFalse);
      expect(jsonDecode(call.body), request('stop'));
      return http.Response(jsonEncode(response('stopped')), 200);
    }));
    expect(
        (await client.liveScreenControl(request('stop')))['state'], 'stopped');
  });
  test('control rejects redirect responses without following them', () async {
    for (final code in [307, 308]) {
      var calls = 0;
      final client = GatewayClient(httpClient: MockClient((call) async {
        calls++;
        expect(call.followRedirects, isFalse);
        return http.Response('', code,
            headers: {'location': 'https://example.org/'});
      }));
      await expectLater(
          client.liveScreenControl(request('stop')), throwsA(isA<Exception>()));
      expect(calls, 1);
      client.close();
    }
  });
  test('missing grant and unsafe session are rejected before dispatch',
      () async {
    var calls = 0;
    final client = GatewayClient(httpClient: MockClient((_) async {
      calls++;
      return http.Response('{}', 200);
    }));
    await expectLater(
        client.liveScreenControl(request('start')..remove('grant_ref')),
        throwsFormatException);
    await expectLater(
        client.liveScreenControl(request('stop')..['session_id'] = '../x'),
        throwsFormatException);
    expect(calls, 0);
  });
  test('duplicate monitor request cannot reach the gateway', () async {
    var calls = 0;
    final client = GatewayClient(httpClient: MockClient((_) async {
      calls++;
      return http.Response('{}', 200);
    }));
    final body = request('open')
      ..['sources'] = [
        {'source_id': 'display:0'},
        {'source_id': 'display:0'}
      ];
    await expectLater(client.liveScreenControl(body), throwsFormatException);
    expect(calls, 0);
  });
  test('wrong session or authority cannot establish stopped state', () async {
    for (final result in [
      response('stopped')..['session_id'] = 'other',
      response('stopped')..['authority'] = {'grant_ref': grant},
      response('active'),
    ]) {
      final client = GatewayClient(
          httpClient:
              MockClient((_) async => http.Response(jsonEncode(result), 200)));
      await expectLater(
          client.liveScreenControl(request('stop')), throwsFormatException);
    }
  });
  test('open response must preserve selected sources and model binding',
      () async {
    final body = request('open')..remove('session_id');
    body.addAll({
      'sources': [
        {'source_id': 'display:0'}
      ],
      'destination': 'route-1',
      'body_session_ref': 'body-1',
      'instrument_ref': 'screen',
      'model': 'vision-model',
      'delivery_mode': 'sampled_image'
    });
    final result = response('created')
      ..addAll({
        'source_ids': ['display:0'],
        'destination': 'route-1',
        'body_binding': {'session_ref': 'body-1', 'instrument_ref': 'screen'},
        'model': 'vision-model',
        'delivery_mode': 'sampled_image'
      });
    final client = GatewayClient(
        httpClient:
            MockClient((_) async => http.Response(jsonEncode(result), 200)));
    expect((await client.liveScreenControl(body))['state'], 'created');
    for (final binding in [
      null,
      {'session_ref': 'other', 'instrument_ref': 'screen'},
      {'session_ref': 'body-1', 'instrument_ref': 'other'}
    ]) {
      result['body_binding'] = binding;
      await expectLater(client.liveScreenControl(body), throwsFormatException);
    }
    result['body_binding'] = {
      'session_ref': 'body-1',
      'instrument_ref': 'screen'
    };
    body['start_immediately'] = true;
    await expectLater(client.liveScreenControl(body), throwsFormatException);
    result['state'] = 'active';
    expect((await client.liveScreenControl(body))['state'], 'active');
    body['start_immediately'] = 'true';
    await expectLater(client.liveScreenControl(body), throwsFormatException);
    body['start_immediately'] = true;
    result['model'] = 'other-model';
    await expectLater(client.liveScreenControl(body), throwsFormatException);
  });
}
