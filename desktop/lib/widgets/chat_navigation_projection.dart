import '../models/chat.dart';
import '../models/chat_index.dart';
import 'chat_navigation_types.dart';

ChatNavigationSnapshot chatNavigationSnapshotFromConversation(
  Conversation conversation,
) {
  final index = buildChatConversationIndex(conversation);
  return ChatNavigationSnapshot(
    outline: [for (final entry in index.outline) _outline(entry)],
    links: [for (final link in index.uniqueLinks) _link(link)],
    bookmarks: [
      for (final bookmark in conversation.bookmarks)
        _bookmark(conversation, bookmark)
    ],
    search: (query) => [for (final hit in index.search(query)) _searchHit(hit)],
  );
}

ChatNavigationItem _outline(ChatIndexEntry entry) => ChatNavigationItem(
      kind: entry.kind == ChatIndexEntryKind.prompt
          ? ChatNavigationKind.prompt
          : ChatNavigationKind.heading,
      title: entry.title,
      subtitle: entry.kind == ChatIndexEntryKind.prompt
          ? 'prompt ${entry.messageIndex + 1}'
          : 'assistant heading',
      target: entry.target,
      level: entry.level,
    );

ChatNavigationItem _link(ChatLinkOccurrence link) => ChatNavigationItem(
      kind: ChatNavigationKind.link,
      title: (link.label == null || link.label!.trim().isEmpty)
          ? link.url
          : link.label!.trim(),
      subtitle: link.url,
      target: link.target,
      url: link.url,
    );

ChatNavigationItem _bookmark(Conversation conversation, ChatBookmark bookmark) {
  final resolved = resolveChatTarget(conversation, bookmark.target);
  final label = bookmark.label.trim();
  return ChatNavigationItem(
    kind: ChatNavigationKind.bookmark,
    title: label.isEmpty ? 'Bookmarked turn' : label,
    subtitle: _precisionLabel(resolved.precision),
    target: bookmark.target,
  );
}

ChatNavigationItem _searchHit(ChatSearchHit hit) => ChatNavigationItem(
      kind: ChatNavigationKind.search,
      title: 'Match in turn ${hit.messageIndex + 1}',
      subtitle: hit.snippet,
      target: hit.target,
    );

String _precisionLabel(ChatTargetPrecision precision) => switch (precision) {
      ChatTargetPrecision.exactOffset => 'source offset exact',
      ChatTargetPrecision.clampedOffset => 'source offset changed',
      ChatTargetPrecision.messageOnly => 'message target',
      ChatTargetPrecision.missing => 'source missing',
    };
