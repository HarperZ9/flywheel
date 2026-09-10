import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/assistant/assistant_executor.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/assistant_panel.dart';

const run = '0123456789abcdef';

void main() {
  testWidgets('lost submission does not claim the run was never started',
      (tester) async {
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.method == 'POST') {
        throw http.ClientException('private failure');
      }
      return http.Response(jsonEncode({'runs': []}), 200);
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: AssistantPanel(
                executor: AssistantExecutor(
                    agent: GatewayAgentSink(client),
                    device: const _Device())))));
    await tester.enterText(
        find.byKey(const Key('assistant-input')), 'check the launch draft');
    await tester.tap(find.text('Send'));
    await tester.pumpAndSettle();
    expect(find.text('submission outcome unknown'), findsOneWidget);
    expect(find.text('could not start the run'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
      'reopened panel reads gateway tasks and separates execution from assurance',
      (tester) async {
    var posts = 0;
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.method == 'POST') posts++;
      final body = switch (request.url.path) {
        '/api/relay/runs' => {
            'runs': [
              {'run_id': run, 'state': 'running'}
            ]
          },
        '/api/relay/status' => {'run_id': run, 'state': 'done'},
        '/api/relay/result' => {
            'run_id': run,
            'state': 'done',
            'result': {
              'verified': false,
              'final_answer': false,
              'chain_ok': true,
              'checkpoint': 'a' * 64,
              'final': 'private result remains in Relay',
            }
          },
        _ => <String, dynamic>{},
      };
      return http.Response(jsonEncode(body), 200);
    }));
    Widget panel() => MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
          body: AssistantPanel(
              executor: AssistantExecutor(
                  agent: GatewayAgentSink(client), device: const _Device())),
        ));
    await tester.pumpWidget(panel());
    await tester.pumpAndSettle();
    expect(find.text('Gateway tasks'), findsOneWidget);
    expect(find.text('Running'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('assistant-task-refresh-$run')));
    await tester.pumpAndSettle();
    expect(find.text('Execution completed'), findsOneWidget);
    expect(find.text('Result needs review'), findsOneWidget);
    expect(find.textContaining('Answer accuracy is not established'),
        findsOneWidget);
    expect(find.textContaining('private result remains'), findsNothing);
    await tester.pumpWidget(const SizedBox());
    await tester.pumpWidget(panel());
    await tester.pumpAndSettle();
    expect(find.text('Running'), findsOneWidget);
    expect(posts, 0);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets(
      'history read failure is visible and does not echo private diagnostics',
      (tester) async {
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response(
            jsonEncode({'error': 'token=do-not-render-this'}), 200)));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
          body: AssistantPanel(
              executor: AssistantExecutor(
                  agent: GatewayAgentSink(client), device: const _Device())),
        )));
    await tester.pumpAndSettle();
    expect(
        find.textContaining('Gateway tasks could not be read'), findsOneWidget);
    expect(find.textContaining('do-not-render-this'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('completed status survives a private result read failure',
      (tester) async {
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.url.path.endsWith('/result')) {
        throw http.ClientException('token=private-result-diagnostic');
      }
      return http.Response(
          jsonEncode(request.url.path.endsWith('/runs')
              ? {
                  'runs': [
                    {'run_id': run, 'state': 'done'}
                  ]
                }
              : {'run_id': run, 'state': 'done'}),
          200);
    }));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: AssistantPanel(
                executor: AssistantExecutor(
                    agent: GatewayAgentSink(client),
                    device: const _Device())))));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('assistant-task-refresh-$run')));
    await tester.pumpAndSettle();
    expect(find.text('Execution completed'), findsOneWidget);
    expect(find.text('Receipt assurance unavailable'), findsOneWidget);
    expect(find.textContaining('result and receipts could not be read'),
        findsOneWidget);
    expect(find.textContaining('private-result-diagnostic'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('narrow panel can refresh a task without overflow',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final client = GatewayClient(
        httpClient: MockClient((_) async => http.Response(
            jsonEncode({
              'runs': [
                {'run_id': run, 'state': 'interrupted'}
              ]
            }),
            200)));
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
          body: AssistantPanel(
              executor: AssistantExecutor(
                  agent: GatewayAgentSink(client), device: const _Device())),
        )));
    await tester.pumpAndSettle();
    expect(find.text('Interrupted'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}

class _Device implements DeviceSink {
  const _Device();
  @override
  Future<bool> open(String deepLink) async => false;
}
