import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/app.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_controller.dart';
import 'package:flywheel_desktop/controllers/rowan_operation_host_adapter.dart';
import 'package:flywheel_desktop/ide/code_buffer_session.dart';
import 'package:flywheel_desktop/ide/unsaved_work_guard.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/code_draft_store.dart';
import 'package:flywheel_desktop/services/gateway_process.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/shell/flywheel_dependencies.dart';
import 'journey_controller_test.dart';

class MemorySettings extends DesktopSettings {
  MemorySettings({super.uiScale});
  int saves = 0;
  @override
  void save() => saves++;
}

class ClosingMockClient extends MockClient {
  ClosingMockClient([Future<http.Response> Function(http.Request)? handler])
      : super(
          handler ??
              ((r) async => http.Response(
                    '{"n_lanes":0,"by_status":{}}',
                    ['/api/world', '/api/lanes'].contains(r.url.path)
                        ? 200
                        : 503,
                  )),
        );
  int closes = 0;
  @override
  void close() {
    closes++;
    super.close();
  }
}

class CountingGatewayProcess extends GatewayProcess {
  CountingGatewayProcess({this.startResult});
  final Completer<String?>? startResult;
  int stops = 0;
  int starts = 0;
  int ownedStops = 0;
  bool owned = false;
  @override
  Future<String?> start({int port = 8799}) async {
    starts++;
    if (startResult == null) return 'test process disabled';
    final error = await startResult!.future;
    owned = error == null;
    return error;
  }

  @override
  void stopIfOwned() {
    stops++;
    if (owned) {
      owned = false;
      ownedStops++;
    }
  }
}

class ShellHarness {
  ShellHarness(
    this.directory, {
    JourneyLens lens = JourneyLens.verify,
    bool seedSession = true,
    Future<http.Response> Function(http.Request)? handler,
    CountingGatewayProcess? gateway,
    CloseChoicePrompt? closePrompt,
  })  : api = ScriptedJourneyApi(),
        settings = MemorySettings(),
        transport = ClosingMockClient(handler),
        process = gateway ?? CountingGatewayProcess() {
    client = GatewayClient(
      baseUrl: 'https://shell.invalid',
      httpClient: transport,
    );
    drafts = JourneyDraftStore(file: File('${directory.path}/drafts.json'));
    sessions = JourneySessionStore(
      file: File('${directory.path}/session.json'),
    );
    if (seedSession) {
      sessions.save(JourneySession(journeyRef: journeyA, lens: lens));
    }
    controller = JourneyController(
      api: api,
      draftStore: drafts,
      sessionStore: sessions,
    );
    rowan = RowanOperationController(client, sessionStore: sessions);
    rowanHost = RowanOperationHostAdapter(rowan);
    code = CodeBufferSession(
      draftStore: CodeDraftStore(root: Directory('${directory.path}/code')),
    );
    dependencies = FlywheelDependencies(
      client: client,
      gateway: process,
      journey: controller,
      rowan: rowan,
      rowanOperationHost: rowanHost,
      code: code,
      closePrompt: closePrompt,
    );
  }
  final Directory directory;
  final ScriptedJourneyApi api;
  final MemorySettings settings;
  final ClosingMockClient transport;
  final CountingGatewayProcess process;
  late final GatewayClient client;
  late final JourneyDraftStore drafts;
  late final JourneySessionStore sessions;
  late final JourneyController controller;
  late final RowanOperationController rowan;
  late final RowanOperationHostAdapter rowanHost;
  late final CodeBufferSession code;
  late final FlywheelDependencies dependencies;

  void replyReady({
    JourneyLens lens = JourneyLens.verify,
    String head = headA,
  }) {
    final value = projection(head: head, lens: lens);
    api
      ..reply('resume:$journeyA:${lens.name}', value)
      ..reply('list', <JourneySummary>[value]);
  }

  Widget app() => FlywheelApp(settings: settings, dependencies: dependencies);
}

Future<void> unmount(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
}
