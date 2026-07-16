// The two operable cards do what they say: the academy lesson runs its
// declared check and binds completion through the callbacks, and the
// marketplace add card parses a command line into argv and env-var names
// without ever holding a value.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/academy_lesson.dart';
import 'package:flywheel_desktop/widgets/marketplace_panel.dart';

Widget _wrap(Widget child) => MaterialApp(
      theme: flywheelLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

void main() {
  testWidgets('a GET lesson runs its check and shows the verdict',
      (tester) async {
    String? ranPath;
    await tester.pumpWidget(_wrap(AcademyLessonCard(
      index: 0,
      lesson: const {
        'id': 'store',
        'title': 'The verifiable substrate',
        'prereqs': [],
        'present': true,
        'teach': 'Store an entity; the receipt is its content hash.',
        'check': {
          'method': 'GET',
          'path': '/api/store/verify',
          'expect': 'ok is true'
        },
      },
      onRunCheck: (path) async {
        ranPath = path;
        return (200, '{"ok": true}');
      },
    )));
    await tester.tap(find.text('Run check'));
    await tester.pumpAndSettle();
    expect(ranPath, '/api/store/verify');
    expect(find.text('RESPONDED 200'), findsOneWidget);
    expect(find.textContaining('"ok": true'), findsOneWidget);
  });

  testWidgets('a POST lesson offers no blind run and completion binds',
      (tester) async {
    String? boundLesson, boundEid;
    await tester.pumpWidget(_wrap(AcademyLessonCard(
      index: 5,
      lesson: const {
        'id': 'forge',
        'title': 'Generation under witness',
        'prereqs': ['oracle'],
        'present': true,
        'teach': 'Survivors carry kernel verdicts.',
        'check': {
          'method': 'POST',
          'path': '/api/invent',
          'expect': 'survivors carry rungs'
        },
      },
      onBind: (lesson, eid) async {
        boundLesson = lesson;
        boundEid = eid;
        return {'bound': true, 'chain_hash': 'abcd1234abcd1234'};
      },
    )));
    expect(find.text('Run check'), findsNothing);
    expect(find.textContaining('runs from its own composer'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'eid-42');
    await tester.tap(find.text('Bind completion'));
    await tester.pumpAndSettle();
    expect(boundLesson, 'forge');
    expect(boundEid, 'eid-42');
    expect(find.text('COMPLETION BOUND'), findsOneWidget);
  });

  testWidgets('a refused binding renders its reason, not silence',
      (tester) async {
    await tester.pumpWidget(_wrap(AcademyLessonCard(
      index: 0,
      lesson: const {
        'id': 'store',
        'title': 'The verifiable substrate',
        'prereqs': [],
        'present': true,
        'teach': 't',
        'check': {'method': 'GET', 'path': '/x', 'expect': 'e'},
      },
      onBind: (lesson, eid) async =>
          {'bound': false, 'reason': 'the referenced receipt did not pass'},
    )));
    await tester.enterText(find.byType(TextField), 'eid-1');
    await tester.tap(find.text('Bind completion'));
    await tester.pumpAndSettle();
    expect(find.textContaining('did not pass'), findsOneWidget);
  });

  testWidgets('the add card parses argv and env names, then reports saved',
      (tester) async {
    String? gotName, gotDetail;
    List<String>? gotCommand, gotRequires;
    await tester.pumpWidget(_wrap(MarketplaceAddCard(
      onAdd: (name, command, detail, requires) async {
        gotName = name;
        gotCommand = command;
        gotDetail = detail;
        gotRequires = requires;
        return {'added': true};
      },
    )));
    await tester.enterText(
        find.widgetWithText(TextField, 'name').first, 'mytool');
    await tester.enterText(
        find.widgetWithText(TextField, 'launch command, e.g. npx -y my-mcp-server'),
        'npx -y mytool-mcp');
    await tester.enterText(
        find.widgetWithText(TextField, 'env var names, comma-separated'),
        'MYTOOL_KEY, OTHER_KEY');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(gotName, 'mytool');
    expect(gotCommand, ['npx', '-y', 'mytool-mcp']);
    expect(gotDetail, '');
    expect(gotRequires, ['MYTOOL_KEY', 'OTHER_KEY']);
    expect(find.text('SAVED'), findsOneWidget);
  });

  testWidgets('a user entry shows yours and offers Remove', (tester) async {
    String? removed;
    await tester.pumpWidget(_wrap(MarketplacePanel(
      doc: const {
        'note': 'n',
        'entries': [
          {
            'name': 'mine',
            'detail': 'my server',
            'command': ['npx', 'mine'],
            'origin': 'user',
            'installed': false,
            'credential_note': '',
          },
          {
            'name': 'filesystem',
            'detail': 'reference',
            'command': ['npx', 'fs'],
            'origin': 'builtin',
            'installed': true,
            'credential_note': '',
          },
        ],
      },
      onInstall: (_) async {},
      onRemoveEntry: (name) async => removed = name,
    )));
    expect(find.text('YOURS'), findsOneWidget);
    expect(find.text('INSTALLED'), findsOneWidget);
    await tester.tap(find.text('Remove'));
    await tester.pumpAndSettle();
    expect(removed, 'mine');
  });
}
