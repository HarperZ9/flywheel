// The keystone: a probed tool's inputSchema becomes a fillable form, and the
// probe carries the full spec (not just a name). These tests hold the schema →
// arguments contract — defaults seeded, required tracked, types coerced — and
// the back-compat fallback to a bare name list.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/models/tool_spec.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/plugin_forms.dart';
import 'package:flywheel_desktop/widgets/tool_form.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

const _demoSchema = {
  'type': 'object',
  'properties': {
    'root': {'type': 'string', 'description': 'the repo root'},
    'count': {'type': 'integer', 'default': 3},
    'deep': {'type': 'boolean'},
    'mode': {
      'type': 'string',
      'enum': ['fast', 'full']
    },
    'tags': {
      'type': 'array',
      'items': {'type': 'string'}
    },
  },
  'required': ['root'],
};

void main() {
  group('ToolSpec parsing', () {
    test('listFromProbe prefers full tool_specs over names', () {
      final specs = ToolSpec.listFromProbe({
        'tools': ['a_tool', 'b_tool'],
        'tool_specs': [
          {'name': 'a_tool', 'description': 'A', 'inputSchema': {}},
          {
            'name': 'b_tool',
            'description': 'B',
            'inputSchema': {
              'type': 'object',
              'properties': {
                'x': {'type': 'string'}
              },
              'required': ['x']
            }
          },
        ],
      });
      expect(specs.map((s) => s.name), ['a_tool', 'b_tool']);
      final b = specs.firstWhere((s) => s.name == 'b_tool');
      expect(b.description, 'B');
      expect(b.requiredFields, {'x'});
      expect(b.hasDeclaredArgs, isTrue);
    });

    test('listFromProbe falls back to bare names for an older probe', () {
      final specs = ToolSpec.listFromProbe({
        'tools': ['x_tool', 'y_tool']
      });
      expect(specs.map((s) => s.name), ['x_tool', 'y_tool']);
      expect(specs.first.hasDeclaredArgs, isFalse);
    });

    test('listFromProbe drops junk entries, never crashes', () {
      final specs = ToolSpec.listFromProbe({
        'tool_specs': [
          null,
          'not-a-map',
          {'name': ''},
          {'name': 'ok'},
        ]
      });
      expect(specs.map((s) => s.name), ['ok']);
    });

    test('fromJson tolerates a non-map inputSchema', () {
      final s = ToolSpec.fromJson({'name': 't', 'inputSchema': 'oops'});
      expect(s.inputSchema, isEmpty);
      expect(s.properties, isEmpty);
      expect(s.requiredFields, isEmpty);
    });
  });

  group('ToolForm schema → arguments', () {
    testWidgets('seeds defaults, tracks required, coerces on edit',
        (tester) async {
      Map<String, dynamic>? args;
      List<String>? missing;
      await tester.pumpWidget(_wrap(ToolForm(
        spec: const ToolSpec(name: 'demo', inputSchema: _demoSchema),
        onChanged: (a, m) {
          args = a;
          missing = m;
        },
      )));
      await tester.pumpAndSettle();

      // A field per property, the required one marked, the type shown.
      expect(find.text('root'), findsOneWidget);
      expect(find.text(' *'), findsOneWidget); // only root is required
      expect(find.text('INTEGER'), findsOneWidget);

      // Default seeded (count: 3); required root still empty → reported missing.
      expect(args, {'count': 3});
      expect(missing, ['root']);

      // Fill the required string (first TextField, schema order).
      await tester.enterText(find.byType(TextField).at(0), 'c:/dev');
      await tester.pump();
      expect(args!['root'], 'c:/dev');
      expect(missing, isEmpty);

      // Toggle the boolean and pick the enum.
      await tester.tap(find.byType(Switch));
      await tester.pump();
      expect(args!['deep'], true);
      await tester.tap(find.byType(DropdownButton<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('full').last);
      await tester.pumpAndSettle();
      expect(args!['mode'], 'full');

      // Array splits on commas/newlines into a typed list (third TextField).
      await tester.enterText(find.byType(TextField).at(2), 'a, b');
      await tester.pump();
      expect(args!['tags'], ['a', 'b']);
    });

    testWidgets('an unparseable number is excluded and flagged',
        (tester) async {
      Map<String, dynamic>? args;
      await tester.pumpWidget(_wrap(ToolForm(
        spec: const ToolSpec(name: 'demo', inputSchema: _demoSchema),
        onChanged: (a, m) => args = a,
      )));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).at(1), 'abc');
      await tester.pump();
      expect(args!.containsKey('count'), isFalse);
      expect(find.text('expects integer'), findsOneWidget);
    });

    testWidgets('an empty schema states it plainly and sends {}',
        (tester) async {
      Map<String, dynamic>? args;
      List<String>? missing;
      await tester.pumpWidget(_wrap(ToolForm(
        spec: const ToolSpec(name: 'bare', inputSchema: {
          'type': 'object',
          'properties': <String, dynamic>{}
        }),
        onChanged: (a, m) {
          args = a;
          missing = m;
        },
      )));
      await tester.pumpAndSettle();
      expect(find.textContaining('declares no arguments'), findsOneWidget);
      expect(args, isEmpty);
      expect(missing, isEmpty);
    });
  });

  group('ProbeResult chips', () {
    testWidgets('renders tool chips and taps back the full spec',
        (tester) async {
      ToolSpec? tapped;
      await tester.pumpWidget(_wrap(ProbeResult(
        probe: const {
          'status': 'live',
          'tools': ['a_tool', 'b_tool'],
          'tool_specs': [
            {'name': 'a_tool', 'description': 'A', 'inputSchema': {}},
            {
              'name': 'b_tool',
              'inputSchema': {
                'type': 'object',
                'properties': {
                  'x': {'type': 'string'}
                },
                'required': ['x']
              }
            },
          ],
        },
        onCallTool: (s) => tapped = s,
      )));
      expect(find.text('a_tool'), findsOneWidget);
      expect(find.text('b_tool'), findsOneWidget);
      expect(find.text('1'), findsOneWidget); // b_tool's arg-count marker
      await tester.tap(find.text('b_tool'));
      await tester.pump();
      expect(tapped!.name, 'b_tool');
      expect(tapped!.requiredFields, {'x'});
    });

    testWidgets('back-compat: a bare name list still yields callable chips',
        (tester) async {
      ToolSpec? tapped;
      await tester.pumpWidget(_wrap(ProbeResult(
        probe: const {
          'status': 'live',
          'tools': ['x_tool'],
        },
        onCallTool: (s) => tapped = s,
      )));
      await tester.tap(find.text('x_tool'));
      await tester.pump();
      expect(tapped!.name, 'x_tool');
      expect(tapped!.hasDeclaredArgs, isFalse);
    });
  });
}
