import 'dart:math';

import 'chat.dart';

enum ChatIndexEntryKind { prompt, heading, link }

final class ChatIndexEntry {
  const ChatIndexEntry({
    required this.kind,
    required this.target,
    required this.title,
    required this.messageIndex,
    required this.offset,
    this.level,
    this.url,
    this.snippet,
  });

  final ChatIndexEntryKind kind;
  final ChatTarget target;
  final String title;
  final int messageIndex;
  final int offset;
  final int? level;
  final String? url;
  final String? snippet;
}

final class ChatSearchHit {
  const ChatSearchHit({
    required this.target,
    required this.messageIndex,
    required this.offset,
    required this.snippet,
  });

  final ChatTarget target;
  final int messageIndex;
  final int offset;
  final String snippet;
}

final class ChatLinkOccurrence {
  const ChatLinkOccurrence({
    required this.target,
    required this.messageIndex,
    required this.offset,
    required this.url,
    this.label,
  });

  final ChatTarget target;
  final int messageIndex;
  final int offset;
  final String url;
  final String? label;
}

final class ChatConversationIndex {
  ChatConversationIndex._({
    required this.outline,
    required this.links,
    required List<ChatMessage> messages,
    required String conversationId,
  })  : _messages = messages,
        _conversationId = conversationId;

  final List<ChatIndexEntry> outline;
  final List<ChatLinkOccurrence> links;
  final List<ChatMessage> _messages;
  final String _conversationId;

  List<ChatLinkOccurrence> get uniqueLinks {
    final seen = <String>{};
    return List.unmodifiable(
      links.where((link) => seen.add(link.url)),
    );
  }

  List<ChatSearchHit> search(String query, {int limit = 50}) {
    final needle = query.trim().toLowerCase();
    if (needle.isEmpty || limit <= 0) return const [];
    final hits = <ChatSearchHit>[];
    for (var messageIndex = 0;
        messageIndex < _messages.length && hits.length < limit;
        messageIndex++) {
      final message = _messages[messageIndex];
      final haystack = message.text.toLowerCase();
      var offset = haystack.indexOf(needle);
      while (offset >= 0 && hits.length < limit) {
        hits.add(ChatSearchHit(
          target: ChatTarget(
            conversationId: _conversationId,
            messageId: message.id,
            offset: offset,
          ),
          messageIndex: messageIndex,
          offset: offset,
          snippet: _snippet(message.text, offset, needle.length),
        ));
        offset = haystack.indexOf(needle, offset + max(1, needle.length));
      }
    }
    return List.unmodifiable(hits);
  }
}

ChatConversationIndex buildChatConversationIndex(Conversation conversation) {
  final outline = <ChatIndexEntry>[];
  final links = <ChatLinkOccurrence>[];
  for (var messageIndex = 0;
      messageIndex < conversation.messages.length;
      messageIndex++) {
    final message = conversation.messages[messageIndex];
    if (message.isUser) {
      final title = _promptTitle(message.text);
      if (title.isNotEmpty) {
        outline.add(ChatIndexEntry(
          kind: ChatIndexEntryKind.prompt,
          target: ChatTarget(
              conversationId: conversation.id,
              messageId: message.id,
              offset: 0),
          title: title,
          messageIndex: messageIndex,
          offset: 0,
        ));
      }
    }
    for (final span in _plainSpans(message.text)) {
      if (!message.isUser) {
        _addHeadings(
          outline,
          conversation.id,
          message,
          messageIndex,
          span,
        );
      }
      _addLinks(links, conversation.id, message, messageIndex, span);
    }
  }
  return ChatConversationIndex._(
    outline: List.unmodifiable(outline),
    links: List.unmodifiable(links),
    messages: List.unmodifiable(conversation.messages),
    conversationId: conversation.id,
  );
}

void _addHeadings(List<ChatIndexEntry> outline, String conversationId,
    ChatMessage message, int messageIndex, _PlainSpan span) {
  var localStart = 0;
  for (final line in span.text.split('\n')) {
    final match = _heading.firstMatch(line);
    if (match != null) {
      final marker = match.group(1)!;
      final title = match.group(2)!.trim();
      final headingOffset = span.offset + localStart + line.indexOf('#');
      outline.add(ChatIndexEntry(
        kind: ChatIndexEntryKind.heading,
        target: ChatTarget(
          conversationId: conversationId,
          messageId: message.id,
          offset: headingOffset,
        ),
        title: title,
        messageIndex: messageIndex,
        offset: headingOffset,
        level: marker.length,
      ));
    }
    localStart += line.length + 1;
  }
}

void _addLinks(List<ChatLinkOccurrence> links, String conversationId,
    ChatMessage message, int messageIndex, _PlainSpan span) {
  final urlRanges = <_Range>[];
  for (final match in _markdownLink.allMatches(span.text)) {
    final urlText = match.group(2)!;
    final offset = span.offset + match.start + match.group(0)!.indexOf(urlText);
    final url = _cleanUrl(urlText);
    urlRanges.add(_Range(offset, offset + urlText.length));
    links.add(_link(conversationId, message, messageIndex, offset, url,
        label: match.group(1)));
  }
  for (final match in _bareLink.allMatches(span.text)) {
    final offset = span.offset + match.start;
    if (urlRanges.any((range) => range.contains(offset))) continue;
    links.add(_link(conversationId, message, messageIndex, offset,
        _cleanUrl(match.group(0)!)));
  }
}

ChatLinkOccurrence _link(String conversationId, ChatMessage message,
        int messageIndex, int offset, String url,
        {String? label}) =>
    ChatLinkOccurrence(
      target: ChatTarget(
          conversationId: conversationId,
          messageId: message.id,
          offset: offset),
      messageIndex: messageIndex,
      offset: offset,
      url: url,
      label: label,
    );

Iterable<_PlainSpan> _plainSpans(String text) sync* {
  var offset = 0;
  var inFence = false;
  String? fenceMarker;
  while (offset <= text.length) {
    final newline = text.indexOf('\n', offset);
    final lineEnd = newline < 0 ? text.length : newline;
    final line = text.substring(offset, lineEnd);
    final fence = _fence.firstMatch(line);
    if (!inFence && fence == null) {
      yield _PlainSpan(offset, line);
    } else if (!inFence && fence != null) {
      inFence = true;
      fenceMarker = fence.group(1)![0];
    } else if (fence != null && fence.group(1)!.startsWith(fenceMarker!)) {
      inFence = false;
      fenceMarker = null;
    }
    if (newline < 0) break;
    offset = lineEnd + 1;
  }
}

String _promptTitle(String text) {
  for (final line in text.split('\n')) {
    final trimmed = line.trim();
    if (trimmed.isNotEmpty) {
      return trimmed.length <= 80 ? trimmed : '${trimmed.substring(0, 80)}…';
    }
  }
  return '';
}

String _snippet(String text, int offset, int length) {
  final start = max(0, offset - 36);
  final end = min(text.length, offset + length + 36);
  return text.substring(start, end).replaceAll(RegExp(r'\s+'), ' ').trim();
}

String _cleanUrl(String value) =>
    value.replaceFirst(RegExp(r'[.,;:!?\x27"\]}]+$'), '');

final _heading = RegExp(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$');
final _fence = RegExp(r'^ {0,3}(```+|~~~+)');
final _markdownLink =
    RegExp(r'\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)', caseSensitive: false);
final _bareLink = RegExp(r'https?:\/\/[^\s<>()\[\]]+', caseSensitive: false);

final class _PlainSpan {
  const _PlainSpan(this.offset, this.text);
  final int offset;
  final String text;
}

final class _Range {
  const _Range(this.start, this.end);
  final int start;
  final int end;
  bool contains(int value) => value >= start && value < end;
}
