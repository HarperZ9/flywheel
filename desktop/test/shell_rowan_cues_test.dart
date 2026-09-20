import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/assistant/lazy_rowan_cue_player.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_recorded_player.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/live_screen_sharing.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/shell/shell_rowan_cues.dart';

import 'journey_shell_harness.dart';
import 'rowan_action_cue_controller_fixtures.dart';
import 'rowan_action_cue_event_binding_fixtures.dart';
import 'rowan_action_cue_recorded_player_fixtures.dart';

const _grant = 'gnt_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _route = 'route-1';
const _model = 'model-1';
const _sourceId = 'display:0';

final _inventory = {
  'sources': [
    {
      'source_id': _sourceId,
      'kind': 'display',
      'label': 'Monitor one',
      'backend': 'test',
      'available': true,
    }
  ],
};

http.Response _json(Object value, [int status = 200]) =>
    http.Response(jsonEncode(value), status);

Map<String, dynamic> _screenStatus(
  String state, {
  Map<String, dynamic>? body,
  String sessionId = 'session-1',
}) {
  final sources = body == null
      ? [_sourceId]
      : [
          for (final row in body['sources'] as List)
            (row as Map<String, dynamic>)['source_id'] as String
        ];
  return {
    'session_id': sessionId,
    'state': state,
    'source_ids': sources,
    'destination': body?['destination'] ?? _route,
    'model': body?['model'] ?? _model,
    'delivery_mode': body?['delivery_mode'] ?? 'sampled_image',
    'authority': {'action': 'live_screen.control', 'grant_ref': _grant},
    if (body != null)
      'body_binding': {
        'session_ref': body['body_session_ref'],
        'instrument_ref': body['instrument_ref'],
      },
  };
}

Future<GatewayAuthorizationOutcome<Map<String, dynamic>>> _approve(
  GatewayOperation operation,
  GatewayOperationSupplier current,
  Future<Map<String, dynamic>> Function(Map<String, dynamic>) dispatch,
) async {
  expect(current()?.operation, operation.operation);
  return GatewayAuthorizationOutcome.value(await dispatch({
    ...operation.operation,
    'schema': gatewayOperationSchema,
    'grant_ref': _grant,
  }));
}

GatewayClient _client(
  Future<http.Response> Function(http.Request request) handler,
) =>
    GatewayClient(
      baseUrl: 'https://shell-rowan.invalid',
      httpClient: MockClient(handler),
    );

Future<void> _startLocalShare(LiveScreenSharing sharing) async {
  await sharing.refreshSources();
  sharing.select({_sourceId});
  await sharing.start(_approve, destination: () => _route, model: () => _model);
  await flushCueBinding();
}

void main() {
  test('startup and pre opt-in local screen event do not create audio player',
      () async {
    var creates = 0;
    final client = _client((request) async {
      if (request.url.path.endsWith('/sources')) return _json(_inventory);
      if (request.url.path.endsWith('/poll')) return _json({'events': []});
      if (request.method == 'GET') return _json(_screenStatus('active'));
      if (request.method == 'POST') {
        return _json(_screenStatus(
          'active',
          body: jsonDecode(request.body) as Map<String, dynamic>,
        ));
      }
      return http.Response('', 503);
    });
    final sharing = LiveScreenSharing(client);
    final host = BindingOperationHost();
    final lazy = LazyRowanCuePlayer(create: () {
      creates++;
      return RowanRecordedAssetCuePlayer(
        assetBundle: FakeAssetBundle({}),
        backend: FakeNativeAudioBackend(),
      );
    });
    final cues = ShellRowanCues(
      operationHost: host,
      screenSharing: sharing,
      player: lazy,
    );

    expect(creates, 0);
    await _startLocalShare(sharing);

    expect(creates, 0);
    expect(cues.controller.telemetry, isEmpty);
    await cues.dispose();
    sharing.dispose();
    host.dispose();
    client.close();
  });

  test('shell emits actual local screen start and suppresses recovered start',
      () async {
    final localClient = _client((request) async {
      if (request.url.path.endsWith('/sources')) return _json(_inventory);
      if (request.url.path.endsWith('/poll')) return _json({'events': []});
      if (request.method == 'GET') return _json(_screenStatus('active'));
      if (request.method == 'POST') {
        return _json(_screenStatus(
          'active',
          body: jsonDecode(request.body) as Map<String, dynamic>,
        ));
      }
      return http.Response('', 503);
    });
    final localSharing = LiveScreenSharing(localClient);
    final localHost = BindingOperationHost();
    final localPlayer = FakeActionCuePlayer();
    final localCues = ShellRowanCues(
      operationHost: localHost,
      screenSharing: localSharing,
      player: localPlayer,
    )..controller.setEnabled(true);

    await _startLocalShare(localSharing);

    expect(localPlayer.played.map((p) => p.recordedClip!.eventId),
        ['privacy.live_screen_on']);
    await localCues.dispose();
    localSharing.dispose();
    localHost.dispose();
    localClient.close();

    Map<String, dynamic>? pendingBody;
    final recoveredClient = _client((request) async {
      if (request.url.path.endsWith('/sources')) return _json(_inventory);
      if (request.url.path.endsWith('/poll')) return _json({'events': []});
      if (request.url.queryParameters.containsKey('body_session_ref')) {
        return _json({
          'schema': 'flywheel.live-screen-session-list/v1',
          'count': 1,
          'sessions': [
            _screenStatus(
              'active',
              body: pendingBody,
              sessionId: 'recovered-1',
            )
          ],
        });
      }
      if (request.method == 'GET') {
        return _json(_screenStatus(
          'active',
          body: pendingBody,
          sessionId: 'recovered-1',
        ));
      }
      pendingBody = jsonDecode(request.body) as Map<String, dynamic>;
      return http.Response('', 503);
    });
    final recoveredSharing = LiveScreenSharing(recoveredClient);
    final recoveredHost = BindingOperationHost();
    final recoveredPlayer = FakeActionCuePlayer();
    final recoveredCues = ShellRowanCues(
      operationHost: recoveredHost,
      screenSharing: recoveredSharing,
      player: recoveredPlayer,
    )..controller.setEnabled(true);

    await recoveredSharing.refreshSources();
    recoveredSharing.select({_sourceId});
    await recoveredSharing.start(
      _approve,
      destination: () => _route,
      model: () => _model,
    );
    expect(recoveredSharing.uncertainOpen, isTrue);
    await recoveredSharing.recover();
    await flushCueBinding();

    expect(recoveredSharing.sessionOrigin, LiveScreenSessionOrigin.recovered);
    expect(recoveredPlayer.played, isEmpty);
    expect(recoveredCues.controller.telemetry, isEmpty);
    await recoveredCues.dispose();
    recoveredSharing.dispose();
    recoveredHost.dispose();
    recoveredClient.close();
  });

  testWidgets('status bar opens Rowan voice controls without device voice',
      (tester) async {
    final directory = Directory.systemTemp.createTempSync('rowan-cues-shell-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final harness = ShellHarness(directory)..replyReady();

    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Rowan voice'));
    await tester.pumpAndSettle();

    expect(find.text('Rowan voice'), findsWidgets);
    expect(find.byKey(const Key('rowan-action-cues-enabled')), findsOneWidget);
    expect(find.text('Only for new live events after opt-in.'), findsOneWidget);

    await unmount(tester);
    expect(tester.takeException(), isNull);
  });
}
