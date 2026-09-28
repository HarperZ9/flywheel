import '../models/chat.dart' show ChatTarget;

enum ChatNavigationKind { prompt, heading, search, link, bookmark }

typedef ChatNavTarget = ChatTarget;
typedef ChatNavigationSearch = List<ChatNavigationItem> Function(String query);

final class ChatNavigationItem {
  const ChatNavigationItem({
    required this.kind,
    required this.title,
    required this.subtitle,
    required this.target,
    this.level,
    this.url,
  });

  final ChatNavigationKind kind;
  final String title;
  final String subtitle;
  final ChatTarget target;
  final int? level;
  final String? url;
}

final class ChatNavigationSnapshot {
  const ChatNavigationSnapshot({
    this.outline = const [],
    this.links = const [],
    this.bookmarks = const [],
    ChatNavigationSearch? search,
  }) : _search = search;

  final List<ChatNavigationItem> outline;
  final List<ChatNavigationItem> links;
  final List<ChatNavigationItem> bookmarks;
  final ChatNavigationSearch? _search;

  static const empty = ChatNavigationSnapshot();

  List<ChatNavigationItem> search(String query) =>
      _search?.call(query) ?? const [];
}
