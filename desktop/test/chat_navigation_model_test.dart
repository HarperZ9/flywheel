import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/services/chat_draft_store.dart';
import 'package:flywheel_desktop/services/chat_store.dart';

void main() {
  test('legacy messages get stable unique ids from conversation and position',
      () {
    final raw = {
      'id': 'café conversation',
      'title': 'Legacy',
      'created_at': 1000,
      'messages': [
        {'role': 'user', 'text': 'same'},
        {'role': 'assistant', 'text': 'same'},
      ],
    };

    final first = Conversation.fromJson(jsonDecode(jsonEncode(raw)));
    final second = Conversation.fromJson(jsonDecode(jsonEncode(raw)));

    expect(first.messages.map((message) => message.id),
        second.messages.map((message) => message.id));
    expect(first.messages.map((message) => message.id).toSet(), hasLength(2));
    expect(
        first.messages.first.id, ChatMessage.legacyId('café conversation', 0));
    expect(first.messages.first.toJson()['id'], first.messages.first.id);
  });

  test('new and streaming messages keep ids independent of mutable text', () {
    final message = ChatMessage(role: 'assistant', text: 'draft');
    final id = message.id;

    message
      ..text = 'draft plus more text'
      ..streaming = true
      ..streaming = false;
    final reloaded = ChatMessage.fromJson(message.toJson());

    expect(message.id, id);
    expect(reloaded.id, id);
    expect(reloaded.text, 'draft plus more text');
  });

  test('malformed and duplicate ids do not alias separate turns', () {
    final conversation = Conversation.fromJson({
      'id': 'c1',
      'messages': [
        {'id': 'msg_${'a' * 32}', 'role': 'user', 'text': 'first'},
        {'id': 'msg_${'a' * 32}', 'role': 'assistant', 'text': 'second'},
        {'id': 'not usable', 'role': 'user', 'text': 'third'},
      ],
    });

    expect(conversation.messages.map((message) => message.id).toSet(),
        hasLength(3));
    expect(conversation.messages[0].id, 'msg_${'a' * 32}');
    expect(conversation.messages[1].id, ChatMessage.legacyId('c1', 1));
    expect(conversation.messages[2].id, ChatMessage.legacyId('c1', 2));
  });

  test('repaired legacy ids cannot collide with retained supplied ids', () {
    final stolenLegacyId = ChatMessage.legacyId('c2', 1);
    final conversation = Conversation.fromJson({
      'id': 'c2',
      'messages': [
        {'id': stolenLegacyId, 'role': 'user', 'text': 'retained'},
        {'id': 'bad id', 'role': 'assistant', 'text': 'repaired'},
      ],
    });

    expect(conversation.messages.map((message) => message.id).toSet(),
        hasLength(2));
    expect(conversation.messages.first.id, stolenLegacyId);
    expect(conversation.messages.last.id, isNot(ChatMessage.legacyId('c2', 1)));
  });

  test('local target URIs round-trip and reject non-local launchable input',
      () {
    final target = ChatTarget(
        conversationId: 'café/convo', messageId: 'msg_${'b' * 32}', offset: 9);
    final uri = target.toLocalUri();

    expect(ChatTarget.tryParseLocalUri(uri), target);
    expect(ChatTarget.tryParseLocalUri('https://example.com'), isNull);
    expect(ChatTarget.tryParseLocalUri('file:///C:/dev/private.md'), isNull);
    expect(
        ChatTarget.tryParseLocalUri('flywheel-chat://conversation/c/message'),
        isNull);
    expect(ChatTarget.fromJsonValue(target.toJsonValue()), target);
  });

  test('targets reject invalid constructor, json, and URI shapes', () {
    final validId = 'msg_${'b' * 32}';

    expect(() => ChatTarget(conversationId: '', messageId: validId),
        throwsArgumentError);
    expect(() => ChatTarget(conversationId: 'c1', messageId: 'bad'),
        throwsArgumentError);
    expect(
        () => ChatTarget(conversationId: 'c1', messageId: validId, offset: -1),
        throwsArgumentError);

    expect(
        ChatTarget.fromJsonValue({
          'conversation_id': 'c1',
          'message_id': 'bad',
        }),
        isNull);
    expect(
        ChatTarget.fromJsonValue({
          'conversation_id': 'c1',
          'message_id': validId,
          'offset': '1',
        }),
        isNull);
    expect(
        ChatTarget.fromJsonValue({
          'conversation_id': 'c1',
          'message_id': validId,
          'offset': 1,
          'extra': true,
        }),
        isNull);

    expect(
        ChatTarget.tryParseLocalUri(
            'flywheel-chat://conversation/c1/message/bad'),
        isNull);
    expect(
        ChatTarget.tryParseLocalUri(
            'flywheel-chat://conversation/c1/message/$validId?offset=-1'),
        isNull);
    expect(
        ChatTarget.tryParseLocalUri(
            'flywheel-chat://conversation/c1/message/$validId?offset=1&url=file:///C:/private.txt'),
        isNull);
    expect(
        ChatTarget.tryParseLocalUri(
            'flywheel-chat://conversation/c1/message/$validId?offset=1&offset=2'),
        isNull);
    expect(
        ChatTarget.tryParseLocalUri(
            'flywheel-chat://conversation/c1/message/$validId?offset=%E2'),
        isNull);

    final missing = ChatTarget.tryParseLocalUri(
        'flywheel-chat://conversation/c1/message/$validId');
    expect(missing, isNotNull);
    expect(resolveChatTarget(Conversation(id: 'c1'), missing!).precision,
        ChatTargetPrecision.missing);
  });

  test('resolution reports clamped, message-only, and missing precision', () {
    final conversation = Conversation(id: 'c1', messages: [
      ChatMessage(id: 'msg_${'c' * 32}', role: 'assistant', text: 'abcdef'),
    ]);
    var resolved = resolveChatTarget(
        conversation,
        ChatTarget(
            conversationId: 'c1', messageId: 'msg_${'c' * 32}', offset: 3));
    expect((resolved.messageIndex, resolved.offset, resolved.precision),
        (0, 3, ChatTargetPrecision.exactOffset));

    conversation.messages.single.text = 'ab';
    resolved = resolveChatTarget(
        conversation,
        ChatTarget(
            conversationId: 'c1', messageId: 'msg_${'c' * 32}', offset: 3));
    expect((resolved.messageIndex, resolved.offset, resolved.precision),
        (0, 2, ChatTargetPrecision.clampedOffset));

    resolved = resolveChatTarget(conversation,
        ChatTarget(conversationId: 'c1', messageId: 'msg_${'c' * 32}'));
    expect((resolved.messageIndex, resolved.offset, resolved.precision),
        (0, null, ChatTargetPrecision.messageOnly));

    resolved = resolveChatTarget(
        conversation,
        ChatTarget(
            conversationId: 'other', messageId: 'msg_${'c' * 32}', offset: 1));
    expect((resolved.messageIndex, resolved.message, resolved.precision),
        (null, null, ChatTargetPrecision.missing));
  });

  test('bookmarks and notes persist without changing chat messages', () {
    final directory = Directory.systemTemp.createTempSync('chat-nav-store-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final file = File('${directory.path}/history.json');
    final message = ChatMessage(
        id: 'msg_${'d' * 32}',
        role: 'assistant',
        text: 'answer',
        attemptRef: 'att_${'e' * 32}',
        receipt: const {'receipt_id': 'r1'});
    final conversation = Conversation(
      id: 'c1',
      notes: 'Working note',
      bookmarks: [
        ChatBookmark(
            target: ChatTarget(
                conversationId: 'c1', messageId: 'msg_${'d' * 32}', offset: 2),
            label: 'Answer')
      ],
      messages: [message],
    );
    final beforeMessage = message.toJson();

    expect(ChatStore(file: file).save([conversation]), isTrue);
    final reloaded = ChatStore(file: file).load().single;

    expect(reloaded.notes, 'Working note');
    expect(reloaded.bookmarks.single.target.messageId, 'msg_${'d' * 32}');
    expect(reloaded.messages.single.toJson(), beforeMessage);
  });

  test('notes-only conversations survive save and load', () {
    final directory = Directory.systemTemp.createTempSync('chat-nav-notes-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final file = File('${directory.path}/history.json');
    final store = ChatStore(file: file);

    expect(
        store.save([Conversation(id: 'c2', notes: 'Keep this note')]), isTrue);
    expect(store.load().single.notes, 'Keep this note');
  });

  test('draft persistence rejects bounded double-encoded local unsafe text',
      () {
    final directory = Directory.systemTemp.createTempSync('chat-nav-private-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final file = File('${directory.path}/drafts.json');

    for (final unsafe in const [
      'open %252Fetc%252Fpasswd',
      'open file%253A%252F%252F%252Fprivate%252Fnote.txt',
      'api%255Fkey%253Dabcdefghijkl',
      '%25%32%46etc%25%32%46passwd',
      'bad encoded byte %E2',
    ]) {
      expect(() => ChatDraftStore(file: file).save(_draft(unsafe)),
          throwsA(isA<ChatDraftStoreException>()));
      expect(file.existsSync(), isFalse);
    }
  });

  test('draft persistence preserves ordinary percent math and http urls', () {
    final directory = Directory.systemTemp.createTempSync('chat-nav-percent-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final store = ChatDraftStore(file: File('${directory.path}/drafts.json'));
    const safeText = '50% complete, 20% of 50 is 10, 100%% literal, '
        'https://example.com/dev/a%252Fb?x=100%25';

    store.save(_draft(safeText));

    expect(store.load().single.text, safeText);
  });

  test('note references escape labels and keep missing targets data-shaped',
      () {
    final target = ChatTarget(
        conversationId: 'c 1', messageId: 'msg_${'f' * 32}', offset: 1);

    expect(chatNoteReference(target, label: 'See [brackets](now)'),
        '[See \\[brackets\\]\\(now\\)](${target.toLocalUri()})');
    expect(ChatTarget.fromJsonValue(null), isNull);
  });
}

ChatDraft _draft(String text) => ChatDraft(
    draftRef: 'chd_${'a' * 32}',
    conversationRef: 'c0',
    text: text,
    state: ChatDraftState.dirty,
    updatedAt: DateTime.parse('2026-09-15T12:00:00Z'));
