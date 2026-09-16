import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/live_screen_recovery.dart';

void main() {
  final request = <String, dynamic>{
    'body_session_ref': 'studio:1',
    'instrument_ref': 'screen',
    'destination': 'route-1',
    'model': 'model-1',
    'delivery_mode': 'sampled_image',
    'sources': [
      {'source_id': 'display:0'}
    ],
  };
  Map<String, dynamic> row() => {
        'session_id': 'session-1',
        'state': 'active',
        'body_binding': {'session_ref': 'studio:1', 'instrument_ref': 'screen'},
        'source_ids': ['display:0'],
        'destination': 'route-1',
        'model': 'model-1',
        'delivery_mode': 'sampled_image',
      };
  Map<String, dynamic> response(List<dynamic> rows) => {
        'schema': 'flywheel.live-screen-session-list/v1',
        'sessions': rows,
        'count': rows.length,
      };
  test('recovery only reads the requested session binding', () async {
    final client = GatewayClient(httpClient: MockClient((call) async {
      expect(call.method, 'GET');
      expect(call.url.path, '/api/live-screen/sessions');
      expect(call.url.queryParameters, {'body_session_ref': 'studio:1'});
      return http.Response(jsonEncode(response([row()])), 200);
    }));
    final result = await recoverLiveScreenSession(client, request);
    expect(result!['session_id'], 'session-1');
    client.close();
  });
  test('empty is inconclusive and duplicate correlation is rejected', () {
    expect(parseRecoveredScreenSession(response([]), request), isNull);
    expect(() => parseRecoveredScreenSession(response([row(), row()]), request),
        throwsFormatException);
  });
  test('other model, source or body instrument cannot be adopted', () {
    for (final wrong in [
      row()..['model'] = 'other',
      row()..['source_ids'] = ['display:1'],
      row()
        ..['body_binding'] = {
          'session_ref': 'studio:1',
          'instrument_ref': 'other'
        },
      row()..['state'] = 'verified',
      row()..['session_id'] = '../escape',
    ]) {
      expect(() => parseRecoveredScreenSession(response([wrong]), request),
          throwsFormatException);
    }
  });
  test('stopped tombstone is retained as a stopped observation', () {
    expect(
        parseRecoveredScreenSession(
            response([row()..['state'] = 'stopped']), request)!['state'],
        'stopped');
  });
}
