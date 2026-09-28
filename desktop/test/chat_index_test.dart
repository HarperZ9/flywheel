import 'package:flutter_test/flutter_test.dart';
import 'package:flywheel_desktop/models/chat.dart';
import 'package:flywheel_desktop/models/chat_index.dart';

void main() {
  test('outline includes user prompts and assistant markdown headings', () {
    final conversation = Conversation(id: 'c1', messages: [
      ChatMessage(id: 'msg_${'1' * 32}', role: 'user', text: 'Find the paper'),
      ChatMessage(
          id: 'msg_${'2' * 32}',
          role: 'assistant',
          text: 'Intro\n## Evidence\nbody\n### Limits\nmore'),
    ]);

    final index = buildChatConversationIndex(conversation);

    expect(
        index.outline.map((entry) => (entry.kind, entry.title, entry.level)), [
      (ChatIndexEntryKind.prompt, 'Find the paper', null),
      (ChatIndexEntryKind.heading, 'Evidence', 2),
      (ChatIndexEntryKind.heading, 'Limits', 3),
    ]);
    expect(index.outline[1].target.messageId, 'msg_${'2' * 32}');
    expect(index.outline[1].offset,
        conversation.messages[1].text.indexOf('## Evidence'));
  });

  test('incomplete fences exclude headings and links from code text', () {
    final conversation = Conversation(id: 'c1', messages: [
      ChatMessage(
          id: 'msg_${'3' * 32}',
          role: 'assistant',
          text:
              'Before https://outside.example\n```dart\n# Fake\nhttps://inside.example\n'),
    ]);

    final index = buildChatConversationIndex(conversation);

    expect(index.outline, isEmpty);
    expect(index.links.map((link) => link.url), ['https://outside.example']);
  });

  test('links are display-dedupable while source occurrences keep offsets', () {
    final text =
        'First [docs](https://example.com/a).\nAgain https://example.com/a';
    final conversation = Conversation(id: 'c1', messages: [
      ChatMessage(id: 'msg_${'4' * 32}', role: 'assistant', text: text),
    ]);

    final index = buildChatConversationIndex(conversation);

    expect(index.links, hasLength(2));
    expect(
        index.uniqueLinks.map((link) => link.url), ['https://example.com/a']);
    expect(index.links.map((link) => link.offset), [
      text.indexOf('https://example.com/a'),
      text.lastIndexOf('https://example.com/a'),
    ]);
    expect(index.links.first.label, 'docs');
  });

  test('30k word search is local and returns exact source offsets', () {
    final late = List.filled(30000, 'context').join(' ');
    final messageText = '$late\nA decisive Résumé fact appears here.';
    final conversation = Conversation(id: 'c-long', messages: [
      ChatMessage(id: 'msg_${'5' * 32}', role: 'user', text: 'start'),
      ChatMessage(id: 'msg_${'6' * 32}', role: 'assistant', text: messageText),
    ]);

    final hits = buildChatConversationIndex(conversation).search('résumé fact');

    expect(hits, hasLength(1));
    expect(hits.single.target.conversationId, 'c-long');
    expect(hits.single.target.messageId, 'msg_${'6' * 32}');
    expect(hits.single.offset, messageText.indexOf('Résumé fact'));
    expect(hits.single.snippet, contains('decisive Résumé fact'));
  });

  test('empty and repeated heading/search inputs stay bounded', () {
    final conversation = Conversation(id: 'c1', messages: [
      ChatMessage(
          id: 'msg_${'7' * 32}',
          role: 'assistant',
          text: '# Same\nbody\n# Same\nsame same same'),
    ]);
    final index = buildChatConversationIndex(conversation);

    expect(index.outline.map((entry) => entry.title), ['Same', 'Same']);
    expect(index.search(''), isEmpty);
    expect(index.search('same', limit: 2), hasLength(2));
  });
}
