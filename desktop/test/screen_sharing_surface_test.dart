import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/controllers/live_screen_sharing.dart';
import 'package:flywheel_desktop/models/gateway_grant_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/screen_sharing_surface.dart';

void main() {
  testWidgets(
      'leaving Studio retains Stop even when Journey approval is unavailable',
      (tester) async {
    final grant = 'gnt_${'b' * 32}';
    final actions = <String>[];
    final client = GatewayClient(httpClient: MockClient((request) async {
      if (request.url.path.endsWith('/sources')) {
        return http.Response(
            jsonEncode({
              'sources': [
                {
                  'source_id': 'display:0',
                  'kind': 'display',
                  'label': 'Primary',
                  'backend': 'test',
                  'available': true
                }
              ]
            }),
            200);
      }
      if (request.method == 'GET') return http.Response('', 503);
      final body = jsonDecode(request.body);
      if (request.url.path.endsWith('/stop')) {
        expect(body, isEmpty);
        expect(request.followRedirects, isFalse);
        actions.add('stop');
        return http.Response(
            jsonEncode({'session_id': 'session-1', 'state': 'stopped'}), 200);
      }
      actions.add(body['control'] as String);
      return http.Response(
          jsonEncode({
            'session_id': 'session-1',
            'state': body['control'] == 'stop' ? 'stopped' : 'active',
            'source_ids': ['display:0'],
            'body_binding': {
              'session_ref': body['body_session_ref'],
              'instrument_ref': body['instrument_ref']
            },
            'destination': 'route-1',
            'model': 'model-1',
            'delivery_mode': 'sampled_image',
            'authority': {'action': 'live_screen.control', 'grant_ref': grant}
          }),
          200);
    }));
    final sharing = LiveScreenSharing(client);
    await sharing.refreshSources();
    sharing.select({'display:0'});
    await sharing.start(
        (operation, current, dispatch) async =>
            GatewayAuthorizationOutcome.value(await dispatch({
              ...operation.operation,
              'schema': gatewayOperationSchema,
              'grant_ref': grant,
            })),
        destination: () => 'route-1',
        model: () => 'model-1');

    var inStudio = true, approvals = 0;
    await tester.pumpWidget(MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: (context, operation, current, dispatch) async {
          approvals++;
          throw StateError('Journey closed');
        },
        child: StatefulBuilder(
            builder: (context, setState) => Scaffold(
                  body: Column(children: [
                    TextButton(
                        onPressed: () => setState(() => inStudio = false),
                        child: const Text('Go to chat')),
                    Expanded(
                        child: inStudio
                            ? SingleChildScrollView(
                                child: ScreenSharingSurface(sharing: sharing))
                            : const Text('Chat destination')),
                    ScreenSharingSurface(sharing: sharing, compact: true),
                  ]),
                )),
      ),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Go to chat'));
    await tester.pumpAndSettle();
    expect(find.text('Chat destination'), findsOneWidget);
    expect(find.text('Screen connection lost; capture may continue'),
        findsOneWidget);
    expect(find.text('Stop sharing'), findsOneWidget);
    await tester.tap(find.text('Stop sharing'));
    await tester.pumpAndSettle();
    expect(approvals, 0);
    expect(actions, ['open', 'stop']);
    expect(sharing.hasSession, isFalse);
    expect(find.text('Stop sharing'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    sharing.dispose();
    client.close();
  });
}
