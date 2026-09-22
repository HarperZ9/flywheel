import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/models/usage_live_selection.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/usage_view.dart';

void main() {
  testWidgets('live usage follows the current endpoint and model selection',
      (tester) async {
    final httpClient = _UsageHttpClient();
    final client =
        GatewayClient(baseUrl: 'http://127.0.0.1:8799', httpClient: httpClient);
    final selection = UsageLiveSelectionController();
    addTearDown(client.close);

    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: UsageView(client: client, alive: true, usageSelection: selection),
    ));
    await tester.pump();
    expect(httpClient.livePaths.last, '/api/usage/live');

    selection.value =
        const UsageLiveSelection(endpoint: 'vllm', model: 'chosen-model');
    await tester.pump();
    await tester.pump();
    expect(httpClient.livePaths.last,
        '/api/usage/live?endpoint=vllm&model=chosen-model');

    selection.value = const UsageLiveSelection(endpoint: 'llamacpp');
    await tester.pump();
    await tester.pump();
    expect(httpClient.livePaths.last, '/api/usage/live?endpoint=llamacpp');

    await tester.pumpWidget(const SizedBox());
  });
}

final class _UsageHttpClient extends http.BaseClient {
  final paths = <String>[];
  Iterable<String> get livePaths =>
      paths.where((path) => path.startsWith('/api/usage/live'));
  var _tick = 0;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    paths.add(request.url.path +
        (request.url.hasQuery ? '?${request.url.query}' : ''));
    _tick++;
    final body = jsonEncode({
      'schema': 'flywheel.usage-live/v1',
      'observed_utc': '2026-09-17T22:00:${_tick.toString().padLeft(2, '0')}Z',
      'models': []
    });
    return http.StreamedResponse(Stream.value(utf8.encode(body)), 200,
        request: request, headers: {'content-type': 'application/json'});
  }
}
