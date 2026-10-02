import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/assistant/desktop_speech_controller.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/services/settings.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/agent_view.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'desktop_speech_controller_test.dart' show FakeSpeech;

const _a = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
const _binding = GatewayJourneyBinding('jrn_$_a', '$_a$_a');
const _delta =
    'data: {"choices":[{"delta":{"content":"The actual answer."}}]}\n\n';
const _receipt = 'data: {"x_receipt":{"id":"receipt"}}\n\ndata: [DONE]\n\n';

Future<void> _mount(WidgetTester tester, DesktopSpeechController speech,
    Future<http.Response> Function() reply,
    {List<Conversation>? history}) async {
  final dir = Directory.systemTemp.createTempSync('rowan-voice-chat-');
  addTearDown(() => dir.deleteSync(recursive: true));
  final store = ChatStore(file: File('${dir.path}/history.json'));
  if (history != null) store.save(history);
  final client = GatewayClient(httpClient: MockClient((request) async {
    if (request.url.path == '/api/endpoints') {
      return http.Response(
          '{"rows":[{"name":"local","backend":"local","credential":"local-none","provider_role":"local","configured":true}]}',
          200);
    }
    if (request.url.path == '/v1/chat/completions') return reply();
    return http.Response('{}', 404);
  }));
  await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
          body: GatewayOperationScope(
              authorize: (_, operation, current, dispatch) =>
                  dispatch(operation.finalBody(_binding, 'gnt_$_a')),
              child: AgentView(
                  client: client,
                  alive: true,
                  settings: DesktopSettings(),
                  speech: speech,
                  chatStore: store,
                  draftStore: ChatDraftStore(
                      file: File('${dir.path}/drafts.json')))))));
  await tester.pumpAndSettle();
}

Future<void> _send(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.pump();
  await tester.ensureVisible(find.byTooltip('Send  (Enter)'));
  await tester.tap(find.byTooltip('Send  (Enter)'));
  await tester.pumpAndSettle();
  await tester
      .runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
  await tester.pumpAndSettle();
}

void main() {
  for (final width in [800.0, 1200.0]) {
    for (final supported in [true, false]) {
      testWidgets(
          'Send stays visible at width $width with speech supported=$supported',
          (tester) async {
        await tester.binding.setSurfaceSize(Size(width, 600));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final backend = FakeSpeech();
        final speech = DesktopSpeechController(
            supported: supported, createOutput: () => backend);
        await _mount(
            tester, speech, () async => http.Response('$_delta$_receipt', 200));
        await tester.enterText(find.byType(TextField), 'First question');
        await tester.pump();
        expect(find.byTooltip('Send  (Enter)').hitTestable(), findsOneWidget);
        if (supported) {
          await tester.tap(find.byKey(const Key('desktop-speech-enabled')));
          await tester.pump();
          expect(find.byTooltip('Send  (Enter)').hitTestable(), findsOneWidget);
        } else {
          expect(find.text('Unavailable'), findsOneWidget);
        }
        await tester.tap(find.byTooltip('Send  (Enter)'));
        await tester.pumpAndSettle();
        await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 20)));
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(TextField), 'Next question');
        await tester.pump();
        expect(find.byTooltip('Send  (Enter)').hitTestable(), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
        speech.dispose();
      });
    }
  }
  for (final action in [
    'mute',
    'stop',
    'disable',
    'new chat',
    'new prompt',
    'mode',
    'background',
    'leave'
  ]) {
    testWidgets('$action interrupts playback through the chat binding',
        (tester) async {
      final pending = Completer<void>();
      final backend = FakeSpeech()..pending = pending;
      final speech = DesktopSpeechController(createOutput: () => backend);
      await _mount(
          tester, speech, () async => http.Response('$_delta$_receipt', 200));
      await tester.tap(find.byKey(const Key('desktop-speech-enabled')));
      await _send(tester, 'Question');
      expect(speech.speaking, isTrue);
      final stops = backend.stops;
      switch (action) {
        case 'mute':
          await tester.tap(find.byKey(const Key('desktop-speech-mute')));
        case 'stop':
          await tester.tap(find.byKey(const Key('desktop-speech-stop')));
        case 'disable':
          await tester.tap(find.byKey(const Key('desktop-speech-enabled')));
        case 'new chat':
          await tester.tap(find.widgetWithText(OutlinedButton, 'New chat'));
        case 'new prompt':
          await _send(tester, 'Next question');
        case 'mode':
          await tester.tap(find.text('agent'));
        case 'background':
          tester.binding
              .handleAppLifecycleStateChanged(AppLifecycleState.inactive);
          tester.binding
              .handleAppLifecycleStateChanged(AppLifecycleState.resumed);
        case 'leave':
          await tester.pumpWidget(const SizedBox());
      }
      await tester.pump();
      expect(backend.stops, greaterThan(stops));
      if (action != 'new prompt') expect(speech.speaking, isFalse);
      pending.complete();
      await tester.pumpAndSettle();
      await tester.pumpWidget(const SizedBox());
      speech.dispose();
    });
  }
  testWidgets('history restore and mid-turn opt-in never replay an old answer',
      (tester) async {
    final backend = FakeSpeech();
    final speech = DesktopSpeechController(createOutput: () => backend);
    final reply = Completer<http.Response>();
    await _mount(tester, speech, () => reply.future, history: [
      Conversation(id: 'history', model: 'local', messages: [
        ChatMessage(role: 'user', text: 'Old question'),
        ChatMessage(
            role: 'assistant', text: 'Old answer', receipt: {'id': 'old'}),
      ])
    ]);
    await _send(tester, 'Pending question');
    await tester.tap(find.byKey(const Key('desktop-speech-enabled')));
    reply.complete(http.Response('$_delta$_receipt', 200));
    await tester.pump();
    await tester
        .runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pumpAndSettle();
    expect(backend.spoken, isEmpty);
    await tester.pumpWidget(const SizedBox());
    speech.dispose();
  });
  testWidgets('tool payloads and duplicate receipt events never become speech',
      (tester) async {
    final backend = FakeSpeech();
    final speech = DesktopSpeechController(createOutput: () => backend);
    const tool =
        'data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"lookup","arguments":"private tool JSON"}}]}}]}\n\n';
    const duplicate = 'data: {"x_receipt":{"id":"receipt"}}\n\n';
    await _mount(tester, speech,
        () async => http.Response('$tool$_delta$duplicate$_receipt', 200));
    await tester.tap(find.byKey(const Key('desktop-speech-enabled')));
    await _send(tester, 'Question');
    expect(backend.spoken, ['The actual answer.']);
    await tester.pumpWidget(const SizedBox());
    speech.dispose();
  });
  testWidgets('explicit opt-in speaks the completed chat answer once',
      (tester) async {
    final backend = FakeSpeech();
    final speech = DesktopSpeechController(createOutput: () => backend);
    await _mount(
        tester, speech, () async => http.Response('$_delta$_receipt', 200));
    expect(find.text('Speak replies'), findsOneWidget);
    await _send(tester, 'First silent question');
    expect(backend.spoken, isEmpty);
    await tester.tap(find.byKey(const Key('desktop-speech-enabled')));
    await tester.pump();
    await _send(tester, 'Second spoken question');
    expect(backend.spoken, ['The actual answer.']);
    expect(
        find.text('The actual answer.', findRichText: true), findsNWidgets(2));
    await tester.pumpWidget(const SizedBox());
    speech.dispose();
  });
  testWidgets('interrupted reply stays visible without spoken completion',
      (tester) async {
    final backend = FakeSpeech();
    final speech = DesktopSpeechController(createOutput: () => backend);
    await _mount(tester, speech,
        () async => http.Response('${_delta}data: [DONE]\n\n', 200));
    await tester.tap(find.byKey(const Key('desktop-speech-enabled')));
    await _send(tester, 'Question');
    expect(backend.spoken, isEmpty);
    expect(find.textContaining('completion is unknown', findRichText: true),
        findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    speech.dispose();
  });
  testWidgets('playback errors retain the answer and composer at narrow width',
      (tester) async {
    tester.view.physicalSize = const Size(450, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final backend = FakeSpeech()..fail = true;
    final speech = DesktopSpeechController(createOutput: () => backend);
    await _mount(
        tester, speech, () async => http.Response('$_delta$_receipt', 200));
    await tester.tap(find.byKey(const Key('desktop-speech-enabled')));
    await _send(tester, 'Question');
    expect(find.textContaining('Speech unavailable'), findsOneWidget);
    expect(find.text('The actual answer.', findRichText: true), findsOneWidget);
    expect(find.byType(TextField), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    speech.dispose();
  });
}
