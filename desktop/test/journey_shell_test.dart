import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/app.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/journey_controller.dart';
import 'package:flywheel_desktop/models/journey_models.dart';
import 'package:flywheel_desktop/services/gateway_process.dart';
import 'package:flywheel_desktop/services/journey_draft_store.dart';
import 'package:flywheel_desktop/services/journey_session_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/shell/flywheel_shell.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:flywheel_desktop/views/journey_view.dart';
import 'package:flywheel_desktop/widgets/side_rail.dart';

import 'journey_controller_test.dart';

class MemorySettings extends DesktopSettings {
  MemorySettings({super.uiScale});
  int saves = 0;
  @override
  void save() => saves++;
}

class ClosingMockClient extends MockClient {
  ClosingMockClient() : super((_) async => http.Response('{}', 503));
  int closes = 0;
  @override
  void close() {
    closes++;
    super.close();
  }
}

class CountingGatewayProcess extends GatewayProcess {
  int stops = 0;
  @override
  void stopIfOwned() => stops++;
}

class ShellHarness {
  ShellHarness(
    this.directory, {
    JourneyLens lens = JourneyLens.verify,
    bool seedSession = true,
  })  : api = ScriptedJourneyApi(),
        settings = MemorySettings(),
        transport = ClosingMockClient(),
        process = CountingGatewayProcess() {
    client =
        GatewayClient(baseUrl: 'https://shell.invalid', httpClient: transport);
    drafts = JourneyDraftStore(file: File('${directory.path}/drafts.json'));
    sessions =
        JourneySessionStore(file: File('${directory.path}/session.json'));
    if (seedSession) {
      sessions.save(JourneySession(journeyRef: journeyA, lens: lens));
    }
    controller =
        JourneyController(api: api, draftStore: drafts, sessionStore: sessions);
    dependencies = FlywheelDependencies(
        client: client, gateway: process, journey: controller);
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

void main() {
  _homeLifecycleTests();
  _restartLensTests();
  _recoveryTests();
}

void _homeLifecycleTests() {
  testWidgets('Journey is home and shell dependencies have one lifecycle',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('journey-shell-home-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final harness = ShellHarness(dir)..replyReady();
    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();
    final rail = tester.widget<SideRail>(find.byType(SideRail));
    expect(rail.destinations.first.label, 'Journey');
    expect(rail.selectedIndex, 0);
    expect(find.byType(JourneyView), findsOneWidget);
    expect(find.text('fact-1'), findsWidgets);
    expect(find.text('engine offline'), findsOneWidget);
    expect(find.bySemanticsLabel('Event head $headA'), findsOneWidget);
    await tester.pumpWidget(harness.app());
    await tester.pump();
    await tester.tap(find.text('Chat'));
    await tester.pump();
    expect(find.byType(AgentView), findsOneWidget);
    await tester.tap(find.text('Journey'));
    await tester.pump();
    expect(find.byType(JourneyView), findsOneWidget);
    expect(harness.api.calls.where((call) => call == resumeA), hasLength(1));
    expect(harness.api.calls.where((call) => call == 'list'), hasLength(1));
    await unmount(tester);
    expect(harness.transport.closes, 1);
    expect(harness.process.stops, 1);
    expect(() => harness.controller.addListener(() {}), throwsFlutterError);
  });
}

void _restartLensTests() {
  testWidgets('all lenses stay equal and restart resumes exact Diagnose data',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('journey-shell-restart-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final first = ShellHarness(dir)..replyReady();
    await tester.pumpWidget(first.app());
    await tester.pumpAndSettle();
    final baseline = first.controller.state.projection!;
    for (final lens in const [
      JourneyLens.rescue,
      JourneyLens.verify,
      JourneyLens.diagnose,
    ]) {
      first.api.reply('resume:$journeyA:${lens.name}', projection(lens: lens));
      await tester.tap(find.byKey(ValueKey('journey-lens-${lens.name}')));
      await tester.pumpAndSettle();
      final current = first.controller.state.projection!;
      expect(current.sameEvidenceAs(baseline), isTrue);
      expect(current.eventHeadSha256, headA);
      expect(current.factIds, const ['fact-1']);
    }
    await unmount(tester);
    final second = ShellHarness(dir, seedSession: false)
      ..replyReady(lens: JourneyLens.diagnose);
    await tester.pumpWidget(second.app());
    await tester.pumpAndSettle();
    final state = second.controller.state;
    expect(state.activeJourneyRef, journeyA);
    expect(state.selectedLens, JourneyLens.diagnose);
    expect(state.projection?.eventHeadSha256, headA);
    expect(state.projection?.factIds, const ['fact-1']);
    expect(find.bySemanticsLabel('Event head $headA'), findsOneWidget);
    await unmount(tester);
  });
}

void _recoveryTests() {
  testWidgets('conflict and typed failure retain draft and accepted evidence',
      (tester) async {
    final dir = Directory.systemTemp.createTempSync('journey-shell-failure-');
    addTearDown(() => dir.deleteSync(recursive: true));
    final harness = ShellHarness(dir)..replyReady();
    await tester.pumpWidget(harness.app());
    await tester.pumpAndSettle();
    final item = draft('append');
    harness.controller.saveDraft(item);
    harness.api
      ..mutation('append', failure('HEAD_CONFLICT'))
      ..reply(resumeA, projection(head: headB));
    await harness.controller.submitAppend(item);
    await tester.pump();
    expect(harness.controller.state.phase, JourneyViewPhase.conflicted);
    expect(harness.drafts.list().single.baseEventHeadSha256, headB);
    expect(harness.controller.state.projection?.eventHeadSha256, headB);
    await tester.scrollUntilVisible(
      find.textContaining('retry the same request'),
      200,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.textContaining('retry the same request'), findsOneWidget);
    harness.api.reply('prepare', failure('AUTH_REQUIRED'));
    await harness.controller.submitAppend(harness.drafts.list().single);
    await tester.pump();
    expect(harness.drafts.list(), hasLength(1));
    expect(harness.controller.state.recoveryActions, {
      JourneyRecoveryAction.authenticate,
      JourneyRecoveryAction.retrySameRequest,
    });
    expect(harness.controller.state.projection?.eventHeadSha256, headB);
    expect(find.text('engine offline'), findsOneWidget);
    expect(find.text('fact-1'), findsWidgets);
    await unmount(tester);
  });
}
