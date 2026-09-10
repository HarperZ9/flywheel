import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/views/endpoints_view.dart';

void main() {
  testWidgets('completion before first pending read refreshes endpoint roster', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 4000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    var done = false, rosterReads = 0;
    final client = GatewayClient(httpClient: MockClient((r) async {
      if (r.url.path == '/api/endpoints') rosterReads++;
      if (r.url.path == '/api/auth/login') {
        done = true;
        return http.Response('{"ok":true,"mode":"browser"}', 200);
      }
      if (r.url.path == '/api/auth') {
        final doc = _auth(pending: false);
        if (!done) (doc['providers'] as List)[0].addAll({'present': false, 'last': ''});
        return http.Response(jsonEncode(doc), 200);
      }
      return http.Response('{}', 200);
    }));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    final before = rosterReads;
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('credential stored'), findsOneWidget);
    expect(rosterReads, greaterThan(before));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('pending beyond 15 seconds automatically reaches stored status', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 4000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    var reads = 0;
    var pending = true;
    final client = GatewayClient(httpClient: MockClient((r) async {
      if (r.url.path == '/api/auth') {
        reads++;
        return http.Response(jsonEncode(_auth(pending: pending)), 200);
      }
      return http.Response('{}', 200);
    }));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    expect(find.textContaining('waiting for the browser'), findsOneWidget);
    await tester.pump(const Duration(seconds: 16));
    await tester.pump();
    expect(reads, greaterThan(1));
    expect(find.text('credential stored'), findsNothing);
    pending = false;
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.text('credential stored'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('status timeout retains unresolved raw request ownership', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 4000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final stalled = Completer<http.Response>();
    var reads = 0;
    final client = GatewayClient(httpClient: MockClient((r) async {
      if (r.url.path == '/api/auth') {
        reads++;
        if (reads > 1) return stalled.future;
        return http.Response(jsonEncode(_auth()), 200);
      }
      return http.Response('{}', 200);
    }));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 2));
    await tester.pump(const Duration(seconds: 20));
    expect(reads, 2);
    expect(find.textContaining('status is taking longer'), findsOneWidget);
    await tester.pump(const Duration(seconds: 30));
    expect(reads, 2);
    await tester.pumpWidget(_app(client, alive: false));
    stalled.complete(http.Response(jsonEncode(_auth(pending: false)), 200));
    await tester.pumpAndSettle();
    expect(find.text('credential stored'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('cancel reaches the endpoint and never renders stored success', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 4000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    var cancelled = false;
    final client = GatewayClient(httpClient: MockClient((r) async {
      if (r.url.path == '/api/auth/cancel') {
        expect(jsonDecode(r.body)['provider'], 'openai');
        cancelled = true;
        return http.Response('{"ok":true,"state":"cancelled"}', 200);
      }
      if (r.url.path == '/api/auth') {
        final doc = _auth();
        if (cancelled) {
          (doc['providers'] as List)[0]['pending'] = false;
          (doc['providers'] as List)[0]['last'] = 'cancelled';
        }
        return http.Response(jsonEncode(doc), 200);
      }
      return http.Response('{}', 200);
    }));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    expect(cancelled, isTrue);
    expect(find.text('sign-in cancelled locally'), findsWidgets);
    expect(find.text('credential stored'), findsNothing);
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('exchange rejection appears automatically without success', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1200, 4000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    var failed = false;
    final client = GatewayClient(httpClient: MockClient((r) async {
      if (r.url.path == '/api/auth') {
        final doc = _auth();
        if (failed) {
          (doc['providers'] as List)[0].addAll({
            'pending': false, 'last': 'failed', 'last_error': 'token exchange rejected (HTTP 400)',
          });
        }
        return http.Response(jsonEncode(doc), 200);
      }
      return http.Response('{}', 200);
    }));
    await tester.pumpWidget(_app(client));
    await tester.pumpAndSettle();
    failed = true;
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.textContaining('HTTP 400'), findsOneWidget);
    expect(find.text('credential stored'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}

Map<String, dynamic> _auth({bool pending = true}) => {
  'credential_store': true,
  'providers': [{
    'provider': 'openai', 'kind': 'registered', 'kind_label': 'registered browser',
    'pending': pending, 'present': !pending, 'last': pending ? 'running' : 'done',
    'source': pending ? 'absent' : 'keychain', 'keychain_name': 'TEST_KEY',
  }],
};

Widget _app(GatewayClient client, {bool alive = true}) => MaterialApp(
  theme: flywheelLightTheme(),
  home: Scaffold(body: EndpointsView(client: client, alive: alive)),
);
