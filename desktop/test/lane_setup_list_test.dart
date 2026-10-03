// lane_setup_list_test.dart - the setup items a lane card states, and the
// two choices made in the app (WP9b).
//
// Choosing node.exe or the local-model project folder picks what the engine
// runs or reads, so each goes through its own exact grant (settings.node_path,
// lane.root) and the engine's refusal is stated in a plain sentence. After a
// kept choice the list reads the lane's setup again. The roster mounts one
// console per lane card, and none on a lane this build holds back.

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
import 'package:flywheel_desktop/widgets/lane_health_panel.dart';
import 'package:flywheel_desktop/widgets/lane_setup_list.dart';

Map<String, dynamic> _item(String id, bool met, String title, String copy) =>
    {'id': id, 'met': met, 'title': title, 'copy': copy};

class _Engine {
  final seen = <http.Request>[];
  final operations = <GatewayOperation>[];
  int settingStatus = 200;
  Map<String, Object> settingBody = const {'id': 'node', 'met': true};
  Map<String, Object> setupBody = const {};

  GatewayClient client() => GatewayClient(
      baseUrl: 'http://engine.invalid',
      httpClient: MockClient((request) async {
        seen.add(request);
        if (request.method == 'GET') {
          return http.Response(jsonEncode(setupBody), 200);
        }
        return http.Response(jsonEncode(settingBody), settingStatus);
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

Widget _app(_Engine engine, Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: GatewayOperationScope(
        authorize: engine.authorize,
        child: Scaffold(body: SingleChildScrollView(child: child)),
      ),
    );

Lane _lane(String name, List<Map<String, dynamic>> setup,
        {String state = 'needs_setup', String code = ''}) =>
    Lane.fromJson({
      'name': name,
      'kind': 'bundled',
      'status': 'declared',
      'state': state,
      'code': code,
      'setup': setup,
    });

void main() {
  testWidgets('choosing node.exe goes through its grant, then setup is read',
      (tester) async {
    final engine = _Engine()
      ..setupBody = {
        'lane': 'learn',
        'items': [
          _item('node', true, 'Node.js 20 or later', 'Node v22.1.0 chosen.')
        ]
      };
    var changed = 0;
    await tester.pumpWidget(_app(
        engine,
        LaneSetupList(
          client: engine.client(),
          lane: _lane('learn', [
            _item('node', false, 'Node.js 20 or later',
                'Install Node.js 20 or later, or choose node.exe.')
          ]),
          pickers: LaneSetupPickers(
              pickNode: () async => r'C:\tools\node\node.exe',
              pickFolder: () async => null),
          onChanged: () => changed++,
        )));
    expect(find.text('NEEDED'), findsOneWidget);
    await tester.tap(find.text('Choose node.exe'));
    await tester.pumpAndSettle();
    final op = engine.operations.single;
    expect(op.action, 'settings.node_path');
    expect(op.destination, const GatewayDestination('setting', 'node_path'));
    expect(op.scopes, ['write', 'exec']);
    expect(engine.seen.first.url.path, '/api/settings/node_path');
    final sent = jsonDecode(engine.seen.first.body) as Map<String, dynamic>;
    expect(sent['path'], r'C:\tools\node\node.exe');
    expect(sent['grant_ref'], 'gnt_test');
    expect(engine.seen.last.url.path, '/api/lanes/learn/setup');
    expect(find.text('MET'), findsOneWidget);
    expect(changed, 1);
  });

  testWidgets('a refused choice is stated from its reason slug',
      (tester) async {
    final engine = _Engine()
      ..settingStatus = 400
      ..settingBody = {
        'code': 'INVALID_REQUEST',
        'error': 'the request is invalid',
        'reason': 'not_a_node_executable'
      };
    await tester.pumpWidget(_app(
        engine,
        LaneSetupList(
          client: engine.client(),
          lane: _lane('learn', [_item('node', false, 'Node', 'Choose it.')]),
          pickers: LaneSetupPickers(
              pickNode: () async => r'C:\tools\node.cmd',
              pickFolder: () async => null),
        )));
    await tester.tap(find.text('Choose node.exe'));
    await tester.pumpAndSettle();
    expect(find.text('Choose a file named node.exe.'), findsOneWidget);
    expect(engine.seen, hasLength(1));
  });

  testWidgets('the local-model folder goes through the lane.root grant',
      (tester) async {
    final engine = _Engine()..setupBody = {'lane': 'local-model', 'items': []};
    await tester.pumpWidget(_app(
        engine,
        LaneSetupList(
          client: engine.client(),
          lane: _lane('local-model', [
            _item('project_folder', false, 'a project folder',
                'Choose a project folder.')
          ]),
          pickers: LaneSetupPickers(
              pickNode: () async => null,
              pickFolder: () async => r'D:\projects\site'),
        )));
    await tester.tap(find.text('Choose folder'));
    await tester.pumpAndSettle();
    final op = engine.operations.single;
    expect(op.action, 'lane.root');
    expect(op.destination,
        const GatewayDestination('setting', 'local-model-root'));
    expect(engine.seen.first.url.path, '/api/lanes/local-model/root');
  });

  testWidgets('a cancelled picker sends nothing', (tester) async {
    final engine = _Engine();
    await tester.pumpWidget(_app(
        engine,
        LaneSetupList(
          client: engine.client(),
          lane: _lane('learn', [_item('node', false, 'Node', 'Choose it.')]),
          pickers: LaneSetupPickers(
              pickNode: () async => null, pickFolder: () async => null),
        )));
    await tester.tap(find.text('Choose node.exe'));
    await tester.pumpAndSettle();
    expect(engine.operations, isEmpty);
    expect(engine.seen, isEmpty);
  });

  testWidgets('each card mounts a console, except a lane held from the build',
      (tester) async {
    final engine = _Engine();
    await tester.pumpWidget(_app(
        engine,
        LaneRosterPanel(
          client: engine.client(),
          lanes: [
            _lane('gather', [_item('git', false, 'Git', 'Install Git.')],
                state: 'limited'),
            _lane('telos', const [], state: 'cannot_launch', code: 'lane_held'),
          ],
        )));
    for (final i in [0, 1]) {
      await tester.tap(find.byType(ExpansionTile).at(i));
      await tester.pumpAndSettle();
    }
    final consoles = tester
        .widgetList<LaneConsole>(find.byType(LaneConsole))
        .map((c) => c.lane.name);
    expect(consoles, ['gather']);
    // The console's setup list states the item; the card does not repeat it.
    expect(find.textContaining('Install Git.'), findsOneWidget);
  });
}
