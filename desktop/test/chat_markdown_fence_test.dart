import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/chat_markdown_body.dart';

Future<void> _pumpMarkdown(
  WidgetTester tester,
  String text, {
  ValueChanged<String>? onOpenUrl,
}) async {
  const size = Size(720, 420);
  await tester.binding.setSurfaceSize(size);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    theme: flywheelLightTheme(),
    home: MediaQuery(
      data: const MediaQueryData(size: size),
      child: Scaffold(
        body: ChatMarkdownBody(text: text, onOpenUrl: onOpenUrl),
      ),
    ),
  ));
}

void main() {
  testWidgets('tilde fenced code keeps URLs and headings inert',
      (tester) async {
    final opened = <String>[];
    const text = 'Intro before code\n'
        '~~~~\n'
        '## Hidden heading\n'
        'https://inside-tilde.example/hidden\n'
        '~~~\n'
        'still code after shorter tilde run\n'
        '~~~~\n'
        '[Outside source](https://outside.example/visible)';

    await _pumpMarkdown(tester, text, onOpenUrl: opened.add);

    expect(find.text('Hidden heading'), findsNothing);
    expect(find.textContaining('## Hidden heading'), findsOneWidget);
    expect(find.textContaining('https://inside-tilde.example/hidden'),
        findsOneWidget);
    expect(find.textContaining('~~~\nstill code'), findsOneWidget);
    expect(find.byKey(const ValueKey('chat-markdown-link-1')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('chat-markdown-link-0')));

    expect(opened, ['https://outside.example/visible']);
  });
}
