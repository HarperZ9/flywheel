// The assistant panel: a typed command carries out and shows an honest result -- a
// device action shows the link it opens, a work request shows the started run id.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/assistant/assistant_executor.dart';
import 'package:flywheel_desktop/assistant/voice.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/assistant_panel.dart';

class _Agent implements AgentSink {
  final List<String> tasks = [];
  @override
  Future<String?> startTask(String goal) async {
    tasks.add(goal);
    return 'run-7';
  }
}

class _Device implements DeviceSink {
  final List<String> opened = [];
  @override
  Future<bool> open(String link) async {
    opened.add(link);
    return true;
  }
}

class _ScriptedVoice implements VoiceInput {
  _ScriptedVoice(this._transcript);
  final String? _transcript;
  @override
  bool get available => true;
  @override
  Future<String?> listen() async => _transcript;
}

class _RecordingVoice implements VoiceOutput {
  final List<String> spoken = [];
  @override
  Future<void> speak(String text) async => spoken.add(text);
}

void main() {
  Widget host(AssistantExecutor ex) => MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: AssistantPanel(executor: ex)),
      );

  testWidgets('a device command shows the reply and the link it opens',
      (tester) async {
    final device = _Device();
    final ex = AssistantExecutor(agent: _Agent(), device: device);
    await tester.pumpWidget(host(ex));

    await tester.enterText(
        find.byKey(const Key('assistant-input')), 'navigate to the pier');
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();

    expect(find.textContaining('directions to the pier'), findsOneWidget);
    expect(device.opened.single, contains('destination=the%20pier'));
  });

  testWidgets('a work command starts a witnessed run and shows its id',
      (tester) async {
    final agent = _Agent();
    final ex = AssistantExecutor(agent: agent, device: _Device());
    await tester.pumpWidget(host(ex));

    await tester.enterText(
        find.byKey(const Key('assistant-input')), 'fix the failing test');
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();

    expect(agent.tasks.single, 'fix the failing test');
    expect(find.textContaining('run run-7'), findsOneWidget);
    expect(find.text('On it. I will start on that and keep the receipts.'),
        findsOneWidget); // the spoken reply, distinct from the panel's description
  });

  testWidgets('a spoken command runs and the reply is spoken back', (tester) async {
    final device = _Device();
    final voiceOut = _RecordingVoice();
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(
        body: AssistantPanel(
          executor: AssistantExecutor(agent: _Agent(), device: device),
          voiceInput: _ScriptedVoice('navigate to home'),
          voiceOutput: voiceOut,
        ),
      ),
    ));

    await tester.tap(find.byKey(const Key('assistant-mic')));
    await tester.pumpAndSettle();

    expect(device.opened.single, contains('destination=home'));
    expect(voiceOut.spoken.single, contains('directions to home'));
  });

  testWidgets('no microphone is shown when no speech engine is present',
      (tester) async {
    await tester.pumpWidget(host(AssistantExecutor(agent: _Agent(), device: _Device())));
    expect(find.byKey(const Key('assistant-mic')), findsNothing);
  });
}
