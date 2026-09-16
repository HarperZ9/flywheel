import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/assistant/rowan_action_cue_controller.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/theme/flywheel_theme.dart';
import 'package:flywheel_desktop/widgets/chat_workspace.dart';

import 'rowan_action_cue_controller_fixtures.dart';

void main() {
  testWidgets('bookmark cue fires only after a new bookmark is durable',
      (tester) async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );
    final conversation = _conversation();

    await _pumpWorkspace(tester, conversation, controller);
    await tester.tap(find.byTooltip('Bookmark turn').first);
    await tester.pump();

    expect(conversation.bookmarks, hasLength(1));
    expect(controller.telemetry.single.kind.wire, 'chat.bookmark_added');
    expect(controller.telemetry.single.eventRef, startsWith('chat_'));
    expect(controller.telemetry.single.provesTaskCorrectness, isFalse);

    await tester.tap(find.byTooltip('Remove bookmark').first);
    await tester.pump();

    expect(conversation.bookmarks, isEmpty);
    expect(controller.telemetry, hasLength(1));
  });

  testWidgets('committed nonempty search cues once and typing stays silent',
      (tester) async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );

    await _pumpWorkspace(tester, _conversation(), controller);
    await tester.tap(find.text('Search'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('chat-nav-search')),
      'Rowan source',
    );
    await tester.pump();

    expect(controller.telemetry, isEmpty);

    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pump();

    expect(controller.telemetry.single.kind.wire, 'chat.history_search');
    expect(controller.telemetry.single.eventRef, startsWith('chat_'));
    expect(controller.telemetry.single.eventRef, isNot(contains('Rowan')));
    expect(controller.telemetry.single.eventRef, isNot(contains('source')));

    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pump();

    expect(controller.telemetry, hasLength(1));
  });

  testWidgets('source jump cue is limited to resolved link source jumps',
      (tester) async {
    final player = FakeActionCuePlayer();
    final controller = RowanActionCueController(
      player: player,
      settings: const RowanActionCueSettings(enabled: true),
    );

    await _pumpWorkspace(tester, _conversation(), controller);
    await tester.tap(find.text('Evidence').last);
    await tester.pump();

    expect(controller.telemetry, isEmpty);

    await tester.tap(find.text('Links'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Jump to source for docs'));
    await tester.pump();

    expect(controller.telemetry.single.kind.wire, 'chat.jump_to_source');
    expect(controller.telemetry.single.eventRef, startsWith('chat_'));
    expect(controller.telemetry.single.eventRef,
        isNot(contains('https://example.com/docs')));
  });
}

Future<void> _pumpWorkspace(
  WidgetTester tester,
  Conversation conversation,
  RowanActionCueController controller,
) async {
  final workspace = ChatWorkspaceController();
  addTearDown(workspace.dispose);
  await tester.binding.setSurfaceSize(const Size(1240, 760));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MaterialApp(
    debugShowCheckedModeBanner: false,
    theme: flywheelLightTheme(),
    home: Scaffold(
      body: ChatWorkspace(
        conversation: conversation,
        controller: workspace,
        onConversationChanged: () {},
        actionCueController: controller,
      ),
    ),
  ));
  await tester.pump(const Duration(milliseconds: 120));
}

Conversation _conversation() {
  final user = ChatMessage(
    id: 'msg_${'1' * 32}',
    role: 'user',
    text: 'Map the Rowan navigation path',
  );
  final assistant = ChatMessage(
    id: 'msg_${'2' * 32}',
    role: 'assistant',
    text: '## Evidence\n'
        'Exact Rowan source fact with [docs](https://example.com/docs).\n'
        'The rest of this answer gives context for local navigation.',
    receipt: const {'receipt_id': 'chat-nav-cues'},
  );
  return Conversation(id: 'cue-chat', messages: [user, assistant]);
}
