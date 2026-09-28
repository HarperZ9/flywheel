const chatLocalUriScheme = 'flywheel-chat';
final _chatMessageId = RegExp(r'^msg_[0-9a-f]{32}$');

bool isChatMessageId(String value) => _chatMessageId.hasMatch(value);

final class ChatTarget {
  ChatTarget({
    required this.conversationId,
    required this.messageId,
    this.offset,
  }) {
    if (conversationId.isEmpty) {
      throw ArgumentError.value(conversationId, 'conversationId');
    }
    if (!isChatMessageId(messageId)) {
      throw ArgumentError.value(messageId, 'messageId');
    }
    if (offset != null && offset! < 0) {
      throw ArgumentError.value(offset, 'offset');
    }
  }

  final String conversationId;
  final String messageId;
  final int? offset;

  String toLocalUri() {
    final query = offset == null ? null : {'offset': '$offset'};
    return Uri(
      scheme: chatLocalUriScheme,
      host: 'conversation',
      pathSegments: [conversationId, 'message', messageId],
      queryParameters: query,
    ).toString();
  }

  Object toJsonValue() => {
        'conversation_id': conversationId,
        'message_id': messageId,
        if (offset != null) 'offset': offset,
      };

  static ChatTarget? fromJsonValue(Object? raw) {
    if (raw is String) return tryParseLocalUri(raw);
    if (raw is! Map) return null;
    final keys = raw.keys.toList(growable: false);
    if (keys.any((key) => key is! String)) return null;
    final keySet = keys.cast<String>().toSet();
    if (!keySet.containsAll(const {'conversation_id', 'message_id'}) ||
        keySet.difference(
            const {'conversation_id', 'message_id', 'offset'}).isNotEmpty) {
      return null;
    }
    final conversationId = raw['conversation_id'];
    final messageId = raw['message_id'];
    final offset = raw['offset'];
    if (conversationId is! String ||
        conversationId.isEmpty ||
        messageId is! String ||
        !isChatMessageId(messageId)) {
      return null;
    }
    if (raw.containsKey('offset') && (offset is! int || offset < 0)) {
      return null;
    }
    return _tryCreate(
        conversationId: conversationId,
        messageId: messageId,
        offset: offset as int?);
  }

  static ChatTarget? tryParseLocalUri(String value) {
    final uri = Uri.tryParse(value);
    late final List<String> pathSegments;
    try {
      pathSegments = uri?.pathSegments ?? const [];
      if (uri == null ||
          uri.scheme != chatLocalUriScheme ||
          uri.host != 'conversation' ||
          pathSegments.length != 3 ||
          pathSegments[1] != 'message') {
        return null;
      }
    } catch (_) {
      return null;
    }
    late final Map<String, List<String>> query;
    try {
      query = uri.queryParametersAll;
    } catch (_) {
      return null;
    }
    if (query.keys.any((key) => key != 'offset')) return null;
    final offsetValues = query['offset'];
    int? offset;
    if (offsetValues != null) {
      if (offsetValues.length != 1) return null;
      offset = _parseUriOffset(offsetValues.single);
      if (offset == null) return null;
    }
    return _tryCreate(
      conversationId: pathSegments[0],
      messageId: pathSegments[2],
      offset: offset,
    );
  }

  static ChatTarget? _tryCreate({
    required String conversationId,
    required String messageId,
    int? offset,
  }) {
    try {
      return ChatTarget(
          conversationId: conversationId, messageId: messageId, offset: offset);
    } catch (_) {
      return null;
    }
  }

  @override
  bool operator ==(Object other) =>
      other is ChatTarget &&
      other.conversationId == conversationId &&
      other.messageId == messageId &&
      other.offset == offset;

  @override
  int get hashCode => Object.hash(conversationId, messageId, offset);
}

int? _parseUriOffset(String value) =>
    RegExp(r'^[0-9]+$').hasMatch(value) ? int.tryParse(value) : null;

final class ChatBookmark {
  const ChatBookmark({
    required this.target,
    this.label = '',
    this.createdAt,
  });

  final ChatTarget target;
  final String label;
  final DateTime? createdAt;

  Map<String, dynamic> toJson() => {
        if (createdAt != null) 'created_at': createdAt!.toIso8601String(),
        if (label.isNotEmpty) 'label': label,
        'target': target.toJsonValue(),
      };

  static ChatBookmark? fromJson(Object? raw) {
    if (raw is! Map) return null;
    final target = ChatTarget.fromJsonValue(raw['target']);
    final label = raw['label'];
    final createdAt = raw['created_at'];
    if (target == null) return null;
    if (label != null && label is! String) return null;
    final parsedCreated =
        createdAt is String ? DateTime.tryParse(createdAt) : null;
    if (createdAt != null && parsedCreated == null) return null;
    return ChatBookmark(
      target: target,
      label: label is String ? label : '',
      createdAt: parsedCreated,
    );
  }
}

String chatNoteReference(ChatTarget target, {String label = ''}) {
  final text = label.trim().isEmpty ? 'source' : label.trim();
  return '[${_escapeMarkdownLinkText(text)}](${target.toLocalUri()})';
}

String _escapeMarkdownLinkText(String value) => value
    .replaceAll(r'\', r'\\')
    .replaceAll('[', r'\[')
    .replaceAll(']', r'\]')
    .replaceAll('(', r'\(')
    .replaceAll(')', r'\)');
