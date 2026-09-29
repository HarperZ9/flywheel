// Shared fixture for the lane console tests: a crucible tool listing, a fake
// engine that records every request and approved operation, and the pump and
// tap helpers.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:flywheel_desktop/client/gateway_client.dart';
import 'package:flywheel_desktop/controllers/gateway_operation_controller.dart';
import 'package:flywheel_desktop/models/lane_models.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/lane_console.dart';

const laneListingFixture = {
  'schema': 'flywheel.lane-tools/v1',
  'lane': 'crucible',
  'n_tools': 4,
  'tools': [
    {
      'name': 'crucible.status',
      'tier': 'T1',
      'admitted': true,
      'listed': true,
      'timeout_s': 20,
      'inputSchema': {},
    },
    {
      'name': 'crucible.run',
      'tier': 'T2',
      'admitted': false,
      'listed': true,
      'timeout_s': 120,
      'inputSchema': {},
    },
    {
      'name': 'crucible.assess',
      'description': 'check a thesis against measurements',
      'tier': 'T1',
      'admitted': true,
      'listed': true,
      'main': true,
      'timeout_s': 30,
      'path_args': ['thesis'],
      'inputSchema': {
        'type': 'object',
        'required': ['thesis'],
        'properties': {
          'thesis': {'type': 'string'},
          'options': {
            'type': 'object',
            'properties': {
              'strict': {'type': 'boolean'}
            }
          },
        },
      },
    },
    {
      'name': 'crucible.refine',
      'tier': 'T2',
      'admitted': false,
      'listed': false,
      'not_in_build': 'numpy_not_in_build',
      'inputSchema': {},
    },
  ],
};

class LaneConsoleEngine {
  final seen = <http.Request>[];
  final operations = <GatewayOperation>[];
  Duration callDelay = Duration.zero;
  int callStatus = 200;
  Object callBody = const {
    'claims': [1, 2, 3],
    'verdict': 'drift'
  };

  GatewayClient client() => GatewayClient(
      baseUrl: 'http://engine.invalid',
      httpClient: MockClient((request) async {
        seen.add(request);
        if (request.url.path == '/api/lanes/crucible/tools') {
          return http.Response(jsonEncode(laneListingFixture), 200);
        }
        await Future<void>.delayed(callDelay);
        return http.Response(jsonEncode(callBody), callStatus);
      }));

  Future<Object?> authorize(
      BuildContext context,
      GatewayOperation operation,
      GatewayOperationSupplier current,
      Future<Object?> Function(Map<String, dynamic>) dispatch) {
    operations.add(operation);
    return dispatch({...operation.operation, 'grant_ref': 'gnt_test'});
  }
}

Lane consoleLane({List<Map<String, dynamic>> setup = const []}) =>
    Lane.fromJson({
      'name': 'crucible',
      'kind': 'bundled',
      'status': 'live',
      'state': 'ready',
      'setup': setup,
    });

Future<void> pumpConsole(WidgetTester tester, LaneConsoleEngine engine,
    {Lane? lane, void Function(String)? onCheck}) async {
  await tester.binding.setSurfaceSize(const Size(900, 2000));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: GatewayOperationScope(
      authorize: engine.authorize,
      child: Scaffold(
        body: SingleChildScrollView(
          child: LaneConsole(
              client: engine.client(),
              lane: lane ?? consoleLane(),
              onCheck: onCheck),
        ),
      ),
    ),
  ));
}

Future<void> listTools(WidgetTester tester) async {
  await tester.tap(find.text('List tools'));
  await tester.pumpAndSettle();
}

Future<void> chooseTool(WidgetTester tester, String label) async {
  await tester.tap(find.text(label));
  await tester.pumpAndSettle();
}

Map<String, dynamic> lastCallBody(LaneConsoleEngine engine) =>
    jsonDecode(engine.seen.last.body) as Map<String, dynamic>;
