import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/chat_workspace.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(_loadCaptureFonts);

  testWidgets('chat navigation renders a wide frame', (tester) async {
    await _pumpFrame(tester, const Size(1240, 760), 1);
    expect(find.text('Outline'), findsOneWidget);
    expect(find.text('Links'), findsOneWidget);
    await expectLater(find.byKey(const ValueKey('chat-nav-capture')),
        matchesGoldenFile('goldens/chat_navigation_wide.png'));
  });

  testWidgets('chat navigation renders a narrow sheet frame', (tester) async {
    await _pumpFrame(tester, const Size(520, 760), 1);
    expect(find.text('Navigate'), findsOneWidget);
    await tester.tap(find.text('Navigate'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 380));
    expect(find.text('Outline'), findsOneWidget);
    await expectLater(find.byType(BottomSheet),
        matchesGoldenFile('goldens/chat_navigation_narrow_sheet.png'));
  });

  testWidgets('chat navigation renders a large text frame', (tester) async {
    await _pumpFrame(tester, const Size(1180, 760), 1.35);
    expect(find.text('Outline'), findsOneWidget);
    await expectLater(find.byKey(const ValueKey('chat-nav-capture')),
        matchesGoldenFile('goldens/chat_navigation_large_text.png'));
  });
}

Future<void> _pumpFrame(
    WidgetTester tester, Size size, double textScale) async {
  await tester.binding.setSurfaceSize(size);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final controller = ChatWorkspaceController();
  addTearDown(controller.dispose);
  await tester.pumpWidget(MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: flywheelLightTheme(),
    home: MediaQuery(
      data: MediaQueryData(
        size: size,
        textScaler: TextScaler.linear(textScale),
      ),
      child: Scaffold(
        body: RepaintBoundary(
          key: const ValueKey('chat-nav-capture'),
          child: ColoredBox(
            color: FwTokens.light.ground,
            child: SizedBox.expand(
              child: ChatWorkspace(
                conversation: _conversation(),
                controller: controller,
                onConversationChanged: () {},
              ),
            ),
          ),
        ),
      ),
    ),
  ));
  await tester.pump(const Duration(milliseconds: 120));
}

Conversation _conversation() {
  final first = ChatMessage(
      id: 'msg_${'1' * 32}',
      role: 'user',
      text: 'Map the Rowan admission path');
  final assistant = ChatMessage(
    id: 'msg_${'2' * 32}',
    role: 'assistant',
    text:
        '## Evidence\nThe gateway records the operation and keeps the UI honest.\n'
        'Read [handoff](https://example.com/handoff) for the source.\n\n'
        '```dart\n// Code links stay inert: https://inside.example\n```\n\n'
        '## Repeated heading\nExact fact: Rowan uses the aperture avatar already in the app.',
    receipt: const {'receipt_id': 'capture-receipt'},
  );
  final conversation =
      Conversation(id: 'capture-chat', messages: [first, assistant]);
  conversation.bookmarks.add(ChatBookmark(
    target: ChatTarget(
      conversationId: conversation.id,
      messageId: assistant.id,
      offset: assistant.text.indexOf('Exact fact'),
    ),
    label: 'Exact Rowan fact',
  ));
  conversation.notes = 'Working note before inserting sources.';
  return conversation;
}

Future<void> _loadCaptureFonts() async {
  final hanken = FontLoader('Hanken Grotesk')
    ..addFont(_assetOrFileFont('assets/fonts/hanken-grotesk-light.ttf'))
    ..addFont(_assetOrFileFont('assets/fonts/hanken-grotesk-regular.ttf'))
    ..addFont(_assetOrFileFont('assets/fonts/hanken-grotesk-medium.ttf'))
    ..addFont(_assetOrFileFont('assets/fonts/hanken-grotesk-semibold.ttf'))
    ..addFont(_assetOrFileFont('assets/fonts/hanken-grotesk-bold.ttf'))
    ..addFont(_assetOrFileFont('assets/fonts/hanken-grotesk-extrabold.ttf'));
  final cascadia = FontLoader('Cascadia Mono')
    ..addFont(_assetOrFileFont('assets/fonts/CascadiaMono.ttf'))
    ..addFont(_assetOrFileFont('assets/fonts/CascadiaMonoItalic.ttf'));
  final icons = FontLoader('MaterialIcons')
    ..addFont(_materialIconsFont());
  await hanken.load();
  await cascadia.load();
  await icons.load();
}

Future<ByteData> _assetOrFileFont(String path) async {
  try {
    return await rootBundle.load(path);
  } catch (_) {
    return _fontData(path);
  }
}

Future<ByteData> _materialIconsFont() async {
  try {
    return await rootBundle.load('fonts/MaterialIcons-Regular.otf');
  } catch (_) {
    final file = _materialIconsFile();
    if (file == null) {
      throw StateError(
          'Material Icons font unavailable in rootBundle, FLUTTER_ROOT, '
          'or ancestors of Platform.resolvedExecutable.');
    }
    return _fontData(file.path);
  }
}

File? _materialIconsFile() {
  const rel = 'bin/cache/artifacts/material_fonts/materialicons-regular.otf';
  final root = Platform.environment['FLUTTER_ROOT'];
  final candidates = <File>[
    if (root != null && root.isNotEmpty) File('$root/$rel'),
  ];
  for (var dir = File(Platform.resolvedExecutable).parent;;) {
    candidates.add(File('${dir.path}/$rel'));
    final parent = dir.parent;
    if (parent.path == dir.path) break;
    dir = parent;
  }
  for (final file in candidates) {
    if (file.existsSync()) return file;
  }
  return null;
}

Future<ByteData> _fontData(String path) async {
  final bytes = await File(path).readAsBytes();
  return ByteData.sublistView(bytes);
}
