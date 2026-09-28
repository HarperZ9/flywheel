import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/chat_markdown_body.dart';
import 'package:flywheel_desktop/widgets/chat_navigation_panel.dart';
import 'package:flywheel_desktop/widgets/chat_navigation_types.dart';
import 'package:flywheel_desktop/widgets/chat_thread.dart';

Future<void> _pump(
  WidgetTester tester,
  Widget child, {
  Size size = const Size(920, 620),
  double textScale = 1,
}) async {
  await tester.binding.setSurfaceSize(size);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: MediaQuery(
      data: MediaQueryData(
        size: size,
        textScaler: TextScaler.linear(textScale),
      ),
      child: Scaffold(body: child),
    ),
  ));
}

void main() {
  testWidgets('thread jumps to a late offscreen target in a long chat',
      (tester) async {
    final jump = ChatThreadJumpController();
    addTearDown(jump.dispose);
    final scroll = ScrollController();
    addTearDown(scroll.dispose);
    final messages = <ChatMessage>[];
    final ids = <String>[];
    for (var i = 0; i < 44; i++) {
      ids.add('msg_${i.toRadixString(16).padLeft(32, '0')}');
      messages.add(ChatMessage(
        id: ids.last,
        role: i.isEven ? 'user' : 'assistant',
        text:
            'Turn $i\n${List.filled(90 + (i % 5) * 18, 'context $i').join(' ')}',
      ));
    }
    final lateId = 'msg_${'f' * 32}';
    final lateText = '${List.filled(4200, 'research').join(' ')}\n'
        '## Repeated heading\nLate source URL https://late.example/source\n'
        'Exact Rowan fact appears here.';
    ids.add(lateId);
    messages.add(ChatMessage(id: lateId, role: 'assistant', text: lateText));

    await _pump(
      tester,
      ChatThread(
        messages: messages,
        controller: scroll,
        messageIds: ids,
        jumpController: jump,
      ),
    );
    await tester.pump();
    final lateBefore = find.textContaining('Late source URL');
    expect(lateBefore, findsOneWidget);
    expect(_withinScreen(tester, lateBefore), isFalse);

    jump.jumpTo(ChatNavTarget(
      conversationId: 'c-long',
      messageId: lateId,
      offset: lateText.indexOf('##'),
    ));
    await tester.pumpAndSettle();

    final late = find.textContaining('Late source URL');
    expect(late, findsOneWidget);
    expect(_withinScreen(tester, late), isTrue);
  });

  testWidgets('thread jumps to source anchor in nonuniform repeated headings',
      (tester) async {
    final jump = ChatThreadJumpController();
    addTearDown(jump.dispose);
    final scroll = ScrollController();
    addTearDown(scroll.dispose);
    const marker = 'MARKER: reviewer target after short lines';
    final shortLines = List.generate(220, (i) => 'short line $i').join('\n');
    final largeTail = List.filled(1800, 'tailword').join(' ');
    final text = '## Repeated heading\nopening instance\n$shortLines\n'
        '## Repeated heading\n$marker\n$largeTail';
    final id = 'msg_${'1' * 32}';

    await _pump(
      tester,
      ChatThread(
        messages: [
          ChatMessage(id: 'msg_${'0' * 32}', role: 'user', text: 'Start'),
          ChatMessage(id: id, role: 'assistant', text: text),
        ],
        controller: scroll,
        jumpController: jump,
      ),
      size: const Size(920, 520),
    );
    final markerFinder = find.textContaining(marker);
    expect(markerFinder, findsOneWidget);
    expect(_withinScreen(tester, markerFinder), isFalse);

    jump.jumpTo(ChatNavTarget(
      conversationId: 'c-nonuniform',
      messageId: id,
      offset: text.indexOf(marker),
    ));
    await tester.pumpAndSettle();

    final rect = tester.getRect(markerFinder);
    final screen = _screenRect(tester);
    debugPrint('source_anchor_jump scroll=${scroll.offset.toStringAsFixed(1)} '
        'max=${scroll.position.maxScrollExtent.toStringAsFixed(1)} '
        'markerTop=${rect.top.toStringAsFixed(1)} '
        'markerBottom=${rect.bottom.toStringAsFixed(1)} '
        'viewport=${screen.height.toStringAsFixed(1)}');
    expect(_withinScreen(tester, markerFinder), isTrue);
  });

  testWidgets('markdown links are explicit and fenced URLs stay inert',
      (tester) async {
    final opened = <String>[];
    final local = <ChatNavTarget>[];
    const targetUri =
        'flywheel-chat://conversation/c1/message/msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa?offset=7';
    await _pump(
      tester,
      ChatMarkdownBody(
        text: 'Open https://early.example/source before '
            '[docs](https://example.com/docs) and '
            '[source]($targetUri).\n```dart\nhttps://inside.example\n```',
        onOpenUrl: opened.add,
        onOpenLocalTarget: local.add,
      ),
    );

    await tester.tap(find.byKey(const ValueKey('chat-markdown-link-0')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('chat-markdown-link-1')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('chat-markdown-link-2')));
    await tester.pump();

    expect(opened, ['https://early.example/source', 'https://example.com/docs']);
    expect(local.single.messageId, 'msg_${'a' * 32}');
    expect(local.single.offset, 7);
    expect(find.text('https://inside.example'), findsOneWidget);
    expect(find.byKey(const ValueKey('chat-markdown-link-3')), findsNothing);
  });

  testWidgets('navigation panel dispatches search links bookmarks and notes',
      (tester) async {
    final semantics = tester.ensureSemantics();
    final selected = <ChatNavTarget>[];
    final opened = <String>[];
    var notes = '';
    final snapshot = ChatNavigationSnapshot(
      outline: [
        ChatNavigationItem(
          kind: ChatNavigationKind.heading,
          title: 'Evidence',
          subtitle: 'assistant',
          target: ChatNavTarget(
              conversationId: 'c1', messageId: 'msg_${'b' * 32}', offset: 4),
          level: 2,
        ),
      ],
      links: [
        ChatNavigationItem(
          kind: ChatNavigationKind.link,
          title: 'docs',
          subtitle: 'https://example.com/docs',
          target: ChatNavTarget(
              conversationId: 'c1', messageId: 'msg_${'c' * 32}', offset: 11),
          url: 'https://example.com/docs',
        ),
      ],
      bookmarks: [
        ChatNavigationItem(
          kind: ChatNavigationKind.bookmark,
          title: 'Pinned fact',
          subtitle: 'assistant',
          target: ChatNavTarget(
              conversationId: 'c1', messageId: 'msg_${'d' * 32}', offset: 3),
        ),
      ],
      search: (query) => query.trim().isEmpty
          ? const []
          : [
              ChatNavigationItem(
                kind: ChatNavigationKind.search,
                title: 'Exact fact',
                subtitle: '... Exact fact inside the late answer ...',
                target: ChatNavTarget(
                    conversationId: 'c1',
                    messageId: 'msg_${'e' * 32}',
                    offset: 90),
              ),
            ],
    );

    await _pump(
      tester,
      ChatNavigationPanel(
        snapshot: snapshot,
        conversationId: 'c1',
        notes: notes,
        sourceReference:
            "[source](flywheel-chat://conversation/c1/message/msg_${'f' * 32}?offset=5)",
        onNotesChanged: (value) => notes = value,
        onTargetSelected: selected.add,
        onOpenUrl: opened.add,
      ),
      size: const Size(360, 620),
      textScale: 1.35,
    );
    for (final label in ['Outline', 'Search', 'Links', 'Bookmarks', 'Notes']) {
      final section = find.text(label);
      final button = find.widgetWithText(TextButton, label);
      expect(section, findsOneWidget);
      expect(button, findsOneWidget);
      expect(_withinScreen(tester, section), isTrue);
      final size = tester.getSize(button);
      expect(size.width, greaterThanOrEqualTo(44));
      expect(size.height, greaterThanOrEqualTo(44));
      expect(
        tester.getSemantics(button),
        matchesSemantics(
          label: label,
          isButton: true,
          hasEnabledState: true,
          isEnabled: true,
          isFocusable: true,
          hasTapAction: true,
          hasFocusAction: true,
        ),
      );
    }

    await tester.tap(find.text('Search'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('chat-nav-search')), 'fact');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Exact fact'));
    await tester.pump();
    expect(selected.last.offset, 90);

    await tester.tap(find.text('Links'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Open docs'));
    await tester.pump();
    await tester.tap(find.byTooltip('Jump to source for docs'));
    await tester.pump();
    expect(opened, ['https://example.com/docs']);
    expect(selected.last.messageId, 'msg_${'c' * 32}');

    await tester.tap(find.text('Bookmarks'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Pinned fact'));
    await tester.pump();
    expect(selected.last.messageId, 'msg_${'d' * 32}');

    await tester.tap(find.text('Notes'));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('chat-nav-notes')), 'Keep this note');
    await tester.pump();
    expect(notes, 'Keep this note');
    semantics.dispose();
  });
}

bool _withinScreen(WidgetTester tester, Finder finder) {
  final rect = tester.getRect(finder);
  final screen = _screenRect(tester);
  return screen.overlaps(rect) && rect.top >= 0 && rect.bottom <= screen.bottom;
}

Rect _screenRect(WidgetTester tester) {
  return Offset.zero & tester.binding.renderViews.single.size;
}
