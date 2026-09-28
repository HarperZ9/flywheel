import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/live_screen_sharing.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';

final grant = 'gnt_${'a' * 32}';
final inventory = {
  'sources': [
    {
      'source_id': 'display:0',
      'kind': 'display',
      'label': 'Monitor one',
      'backend': 'test',
      'available': true
    }
  ]
};
Map<String, dynamic> status(String state) => {
      'session_id': 'session-1',
      'state': state,
      'source_ids': ['display:0'],
      'destination': 'route-1',
      'model': 'model-1',
      'delivery_mode': 'sampled_image',
      'authority': {'action': 'live_screen.control', 'grant_ref': grant},
    };
http.Response json(Object value) => http.Response(jsonEncode(value), 200);
Future<GatewayAuthorizationOutcome<Map<String, dynamic>>> approve(
    GatewayOperation operation,
    GatewayOperationSupplier current,
    Future<Map<String, dynamic>> Function(Map<String, dynamic>)
        dispatch) async {
  expect(current()?.operation, operation.operation);
  return GatewayAuthorizationOutcome.value(await dispatch({
    ...operation.operation,
    'schema': gatewayOperationSchema,
    'grant_ref': grant,
  }));
}

void main() {
  test(
      'lost response recovery remains unresolved on empty or mismatched lookup',
      () async {
    Map<String, dynamic>? dispatched;
    var lookup = <Map<String, dynamic>>[];
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.url.path.endsWith('/sources')) return json(inventory);
      if (request.method == 'POST') {
        dispatched = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response('', 503);
      }
      if (request.url.queryParameters.containsKey('body_session_ref')) {
        expect(request.url.queryParameters['body_session_ref'],
            dispatched!['body_session_ref']);
        return json({
          'schema': 'flywheel.live-screen-session-list/v1',
          'count': lookup.length,
          'sessions': lookup
        });
      }
      return http.Response('', 503);
    }));
    final sharing = LiveScreenSharing(client);
    await sharing.refreshSources();
    sharing.select({'display:0'});
    await sharing.start(approve,
        destination: () => 'route-1', model: () => 'model-1');
    await sharing.recover();
    expect(sharing.uncertainOpen, isTrue);
    lookup = [
      status('active')
        ..['body_binding'] = {
          'session_ref': dispatched!['body_session_ref'],
          'instrument_ref': 'screen'
        }
        ..['model'] = 'other'
    ];
    await sharing.recover();
    expect(sharing.sessionId, isNull);
    expect(sharing.uncertainOpen, isTrue);
    lookup.single['model'] = 'model-1';
    await sharing.recover();
    expect(sharing.sessionId, 'session-1');
    expect(sharing.uncertainOpen, isFalse);
    expect(sharing.hasSession, isTrue); // Even when feed status cannot be read.
    expect(sharing.sessionOrigin, LiveScreenSessionOrigin.recovered);
    sharing.dispose();
    client.close();
  });
  test('lost open response prevents duplicate capture until recovered',
      () async {
    var opens = 0;
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.method == 'GET') return json(inventory);
      opens++;
      return http.Response('', 503);
    }));
    final sharing = LiveScreenSharing(client);
    await sharing.refreshSources();
    sharing.select({'display:0'});
    await sharing.start(approve,
        destination: () => 'route-1', model: () => 'model-1');
    final correlation = sharing.bodySessionRef;
    expect(sharing.hasUnresolvedCapture, isTrue);
    expect(sharing.sessionId, isNull);
    await sharing.start(approve,
        destination: () => 'route-1', model: () => 'model-1');
    expect(opens, 1);
    expect(sharing.bodySessionRef, correlation);
    sharing.dispose();
    client.close();
  });
  test('source discovery and denied start never create capture', () async {
    final methods = <String>[];
    final client = GatewayClient(httpClient: MockClient((request) async {
      methods.add(request.method);
      return json(inventory);
    }));
    final sharing = LiveScreenSharing(client);
    await sharing.refreshSources();
    sharing.select({'display:0'});
    await sharing.start(
        (op, current, dispatch) async =>
            const GatewayAuthorizationOutcome.denied(),
        destination: () => 'route-1',
        model: () => 'model-1');
    expect(methods, ['GET']);
    expect(sharing.hasSession, isFalse);
    expect(sharing.sessionOrigin, isNull);
    sharing.dispose();
    client.close();
  });

  test('one approved open starts capture and failed read retains stop handle',
      () async {
    final controls = <String>[];
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.url.path.endsWith('/sources')) return json(inventory);
      if (request.method == 'GET') return http.Response('unavailable', 503);
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      if (request.url.path.endsWith('/stop')) {
        expect(body, isEmpty);
        controls.add('stop');
        return json(status('stopped'));
      }
      controls.add(body['control'] as String);
      if (body['control'] == 'open') {
        expect(body['start_immediately'], isTrue);
        return json(status('active')
          ..['body_binding'] = {
            'session_ref': body['body_session_ref'],
            'instrument_ref': body['instrument_ref']
          });
      }
      return json(status('stopped'));
    }));
    final sharing = LiveScreenSharing(client);
    await sharing.refreshSources();
    sharing.select({'display:0'});
    await sharing.start(approve,
        destination: () => 'route-1', model: () => 'model-1');
    expect(sharing.sessionId, 'session-1');
    expect(sharing.hasSession, isTrue);
    expect(sharing.sessionOrigin, LiveScreenSessionOrigin.localStart);
    sharing.select({});
    expect(sharing.selected, {'display:0'});
    await sharing.control('stop',
        (op, current, dispatch) async => throw StateError('Journey closed'));
    expect(controls, ['open', 'stop']);
    expect(sharing.hasSession, isFalse);
    sharing.dispose();
    client.close();
  });

  test('wrong stop acknowledgement cannot discard capture handle', () async {
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.url.path.endsWith('/sources')) return json(inventory);
      if (request.method == 'GET') return http.Response('', 503);
      final body = jsonDecode(request.body);
      return json(status(body['control'] == 'open' ? 'active' : 'stopped')
        ..['body_binding'] = {
          'session_ref': body['body_session_ref'],
          'instrument_ref': body['instrument_ref']
        }
        ..['session_id'] = body['control'] == 'open' ? 'session-1' : 'other');
    }));
    final sharing = LiveScreenSharing(client);
    await sharing.refreshSources();
    sharing.select({'display:0'});
    await sharing.start(approve,
        destination: () => 'route-1', model: () => 'model-1');
    await sharing.control('stop', approve);
    expect(sharing.hasSession, isTrue);
    expect(sharing.error, contains('unknown'));
    sharing.dispose();
    client.close();
  });

  test('pending approval re-reads exact model selection', () async {
    var model = 'model-1';
    final client =
        GatewayClient(httpClient: MockClient((_) async => json(inventory)));
    final sharing = LiveScreenSharing(client);
    await sharing.refreshSources();
    sharing.select({'display:0'});
    await sharing.start((operation, current, dispatch) async {
      model = 'model-2';
      expect(operation.operation['model'], 'model-1');
      expect(current()!.operation['model'], 'model-2');
      return const GatewayAuthorizationOutcome.denied();
    }, destination: () => 'route-1', model: () => model);
    expect(sharing.hasSession, isFalse);
    sharing.dispose();
    client.close();
  });
}
