// The history banner says what history could not do and opens the archive
// read-only (design 7.9, FW-13).
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/services/chat_store.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/chat_history_banner.dart';

Future<void> _pump(WidgetTester tester, ChatStore store,
        ValueChanged<String> onDelete) =>
    tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(
            body: ChatHistoryBanner(
                store: store, onDeleteArchived: onDelete))));

void main() {
  late Directory home;
  setUp(() => home = Directory.systemTemp.createTempSync('chat-banner-'));
  tearDown(() => home.deleteSync(recursive: true));

  testWidgets('a set-aside file is named and nothing is said deleted',
      (tester) async {
    final file = File('${home.path}/chats.json')..writeAsStringSync('[oops');
    final store = ChatStore(file: file);
    await tester.runAsync(() async => store.load());
    await _pump(tester, store, (_) {});
    final path = store.quarantinedFiles().single.path;
    expect(find.textContaining('set aside at $path'), findsOneWidget);
    expect(find.textContaining('Nothing was deleted.'), findsOneWidget);
    expect(find.text('Delete this file'), findsOneWidget);
  });

  testWidgets('archived conversations open read-only and delete by id',
      (tester) async {
    final file = File('${home.path}/chats.json');
    final store = ChatStore(file: file);
    final conversations = [
      for (var n = 60; n >= 0; n--)
        Conversation(
            id: 'c$n',
            title: 'topic $n',
            messages: [ChatMessage(role: 'user', text: 'question $n')])
    ];
    await tester.runAsync(() async {
      store.save(conversations);
      store.load();
    });
    String? deleted;
    await _pump(tester, store, (id) => deleted = id);
    expect(find.text('1 archived conversation'), findsOneWidget);

    await tester.tap(find.text('Show'));
    await tester.pumpAndSettle();
    expect(find.text('topic 0'), findsOneWidget);
    expect(find.text('Read-only'), findsOneWidget);

    await tester.tap(find.text('topic 0'));
    await tester.pumpAndSettle();
    expect(find.text('You: question 0'), findsOneWidget);
    expect(find.byType(TextField), findsNothing);

    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    expect(find.text('Delete this conversation?'), findsOneWidget);
    await tester.tap(find.text('Delete').last);
    await tester.pumpAndSettle();
    expect(deleted, 'c0');
  });

  testWidgets('a clean history shows nothing', (tester) async {
    final store = ChatStore(file: File('${home.path}/chats.json'));
    await tester.runAsync(() async => store.load());
    await _pump(tester, store, (_) {});
    expect(find.byType(Text), findsNothing);
  });

  testWidgets('the conversation delete asks first and Keep keeps it',
      (tester) async {
    bool? answer;
    await tester.pumpWidget(MaterialApp(
        theme: flywheelLightTheme(),
        home: Scaffold(body: Builder(
            builder: (context) => TextButton(
                onPressed: () async =>
                    answer = await confirmConversationDelete(context),
                child: const Text('open'))))));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text('Delete this conversation?'), findsOneWidget);
    expect(find.textContaining('no undo'), findsOneWidget);
    await tester.tap(find.text('Keep'));
    await tester.pumpAndSettle();
    expect(answer, isFalse);
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(answer, isTrue);
  });

  testWidgets('deleting a set-aside file says it may still hold text',
      (tester) async {
    final file = File('${home.path}/chats.json')..writeAsStringSync('[oops');
    final store = ChatStore(file: file);
    await tester.runAsync(() async => store.load());
    await _pump(tester, store, (_) {});
    await tester.tap(find.text('Delete this file'));
    await tester.pumpAndSettle();
    expect(find.textContaining('could not parse it'), findsOneWidget);
    expect(find.textContaining('nothing in it can be kept'), findsNothing);
  });
}
