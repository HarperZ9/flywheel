import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/client/journey_api.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/connection_state.dart';
import 'package:flywheel_desktop/models/endpoint_models.dart';
import 'package:flywheel_desktop/models/endpoint_row.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/gateway_status.dart';
import 'package:flywheel_desktop/shell/gateway_status_coordinator.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/journey_view.dart';
import 'package:flywheel_desktop/widgets/endpoint_details.dart';
import 'journey_controller_test.dart';
import 'journey_shell_test.dart' show ShellHarness, unmount;

const declaredStatus = {
  'schema': 'flywheel.desktop-status/v1',
  'status': 'ok',
  'compatible': true,
  'lanes_live': 0,
  'lanes_total': 15,
  'lanes_declared': 15,
  'lanes_missing': 0,
  'lanes_stale': 0,
  'lane_readiness': 'unprobed',
};

void main() {
  testWidgets(
      'shell waits for engine then resumes, and reconnect only refreshes',
      (t) async {
    final dir = Directory.systemTemp.createTempSync('readiness-shell-');
    addTearDown(() => dir.deleteSync(recursive: true));
    var online = false;
    final h = ShellHarness(dir,
        handler: (_) async =>
            http.Response('{"n_lanes":0,"by_status":{}}', online ? 200 : 503))
      ..replyReady();
    await t.pumpWidget(h.app());
    await t.pumpAndSettle();
    expect(h.api.calls, isEmpty);
    online = true;
    await t.pump(const Duration(seconds: 5));
    await t.pumpAndSettle();
    expect(h.api.calls, [resumeA, 'list']);
    expect(find.text('fact-1'), findsWidgets);
    await t.pump(const Duration(seconds: 5));
    await t.pumpAndSettle();
    expect(h.api.calls, [resumeA, 'list']);
    online = false;
    await t.pump(const Duration(seconds: 5));
    await t.pumpAndSettle();
    h.api.reply(resumeA, projection());
    online = true;
    await t.pump(const Duration(seconds: 5));
    await t.pumpAndSettle();
    expect(h.api.calls, [resumeA, 'list', resumeA]);
    await unmount(t);
  });

  test('missing inventory fields cannot become a zero-lane claim', () async {
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response('{}', 200)));
    await expectLater(client.laneRoster(), throwsFormatException);
  });

  test('actual unprobed status contract has no live claim', () {
    final status = ConnectionStatus.fromStatusDoc(declaredStatus);
    expect(status.phase, ConnectionPhase.online);
    expect(status.detail, contains('15 not probed'));
    expect(status.detail, isNot(contains('0/15 lanes live')));
    expect(
        ConnectionStatus.fromStatusDoc(
            {...declaredStatus, 'lane_readiness': 'unknown'}).detail,
        contains('unknown'));
  });

  test('omitted subscription fields remain unknown; roster counts CLI presence',
      () {
    final legacy = EndpointHealthDoc.fromJson({'local': [], 'enterprise': []});
    expect(legacy.subscriptionAvailable, isNull);
    expect(legacy.enterpriseUsable, isNull);
    final row = EndpointRow.fromJson({
      'name': 'codex-cli',
      'backend': 'cli',
      'credential': 'cli-auth',
      'configured': true
    });
    expect(row.cliPresent, isTrue);
  });

  testWidgets('CLI presence is not rendered as verified authentication',
      (t) async {
    await t.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: ProviderRoster(roster: [
          EndpointRow.fromJson({'name': 'codex-cli', 'credential': 'cli-auth'})
        ]))));
    expect(find.text('CLI PRESENT'), findsOneWidget);
    expect(find.text('SUBSCRIPTION'), findsNothing);
  });

  test(
      'readiness edge initializes once and reconnect recovers, without model probes',
      () async {
    var online = false;
    var reads = 0;
    final paths = <String>[];
    final client = GatewayClient(httpClient: MockClient((r) async {
      paths.add(r.url.toString());
      return http.Response(
          jsonEncode(r.url.path == '/api/lanes'
              ? {
                  'n_lanes': 15,
                  'by_status': {'declared': 15},
                  'lanes': []
                }
              : <String, dynamic>{}),
          200);
    }));
    final c = GatewayStatusCoordinator(
        client: client,
        status: GatewayStatusService(
            statusEndpoint: (_) async => online
                ? const GatewayStatusDoc(declaredStatus)
                : const GatewayStatusFailure(0)),
        startEngine: () async => null,
        onReady: () async {
          reads++;
        });
    addTearDown(c.dispose);
    await c.poll();
    expect(reads, 0);
    online = true;
    await Future.wait([c.poll(), c.poll()]);
    await c.poll();
    expect(reads, 1);
    expect(c.message, contains('15 not probed'));
    online = false;
    await c.poll();
    online = true;
    await c.poll();
    expect(reads, 2);
    expect(
        paths.every((p) => !p.contains('probe=true') && !p.contains('health')),
        isTrue);
    await c.probeLanes();
    expect(c.message, contains('15 unverified'));
    expect(c.message, isNot(contains('not probed')));
    expect(paths.last, contains('probe=true'));
  });

  test(
      'transport failure differs from malformed response and never leaks error text',
      () async {
    for (final transport in [true, false]) {
      final api =
          GatewayJourneyApi(GatewayClient(httpClient: MockClient((_) async {
        if (transport) throw http.ClientException('private token-like detail');
        return http.Response('invalid json', 200);
      })));
      await expectLater(
          api.list(),
          throwsA(isA<JourneyApiException>()
              .having((e) => e.failure.code, 'code',
                  transport ? 'GATEWAY_UNREACHABLE' : 'INVALID_RESPONSE')
              .having((e) => e.failure.detail.contains('private'),
                  'private detail', false)));
    }
  });

  test('read retry coalesces and never resends pending mutations', () async {
    final api = ScriptedJourneyApi();
    final h = await readyHarness(api);
    final pending = Completer<JourneyMutationAck>();
    api.mutation('append', pending.future);
    api.reply(resumeA, projection(head: headB));
    api.reply(resumeA, projection(head: headB));
    final sending = h.controller.submitAppend(draft('append'));
    await api.waitFor('append');
    final a = h.controller.retryRead();
    final b = h.controller.retryRead();
    expect(api.calls.where((c) => c == resumeA), isEmpty);
    pending.complete(acknowledgement());
    await Future.wait([sending, a, b]);
    expect(api.calls.where((c) => c == 'append').length, 1);
    expect(api.calls.where((c) => c == resumeA).length, 2);
  });

  testWidgets('failed initial read has actionable read-only retry', (t) async {
    final api = ScriptedJourneyApi();
    final h = ControllerHarness(api);
    addTearDown(h.dispose);
    api.reply('list', failure('GATEWAY_UNREACHABLE'));
    await h.controller.initialize();
    api.reply('list', <JourneySummary>[]);
    await t.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: JourneyView(controller: h.controller))));
    await t.tap(find.widgetWithText(OutlinedButton, 'Retry Journey read'));
    await t.pumpAndSettle();
    expect(h.controller.state.remoteFailure, isNull);
    expect(api.calls, ['list', 'list']);
  });
}
