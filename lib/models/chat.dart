// chat.dart — the conversation model for the Chat surface. A conversation is a
// list of turns; each assistant turn can carry a quiet receipt (the re-derivable
// proof of the turn), so accountability rides underneath the experience without
// being the headline. Pure data; the view owns streaming and persistence.

class ChatMessage {
  final String role; // 'user' | 'assistant'
  String text; // mutable so a streaming assistant turn grows in place
  bool streaming;
  Map<String, dynamic>? receipt; // the turn's x_receipt, when the engine returned one
  Map<String, dynamic>? run; // an agent-mode run result (evidence + verdict), when used

  ChatMessage({
    required this.role,
    this.text = '',
    this.streaming = false,
    this.receipt,
    this.run,
  });

  bool get isUser => role == 'user';

  /// The wire shape the gateway's /v1/chat/completions expects.
  Map<String, String> toWire() => {'role': role, 'content': text};

  /// Durable shape (the transient streaming/run fields are not persisted).
  Map<String, dynamic> toJson() => {
        'role': role,
        'text': text,
        if (receipt != null) 'receipt': receipt,
      };

  factory ChatMessage.fromJson(Map<String, dynamic> j) => ChatMessage(
        role: j['role'] == 'user' ? 'user' : 'assistant',
        text: j['text'] is String ? j['text'] as String : '',
        receipt: j['receipt'] is Map<String, dynamic>
            ? j['receipt'] as Map<String, dynamic>
            : null,
      );
}

class Conversation {
  final String id;
  String title;
  final List<ChatMessage> messages;
  String? model; // the endpoint this conversation is talking to
  final DateTime createdAt;

  Conversation({
    required this.id,
    this.title = 'New chat',
    List<ChatMessage>? messages,
    this.model,
    DateTime? createdAt,
  })  : messages = messages ?? [],
        createdAt = createdAt ?? DateTime.now();

  bool get isEmpty => messages.isEmpty;

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        if (model != null) 'model': model,
        'created_at': createdAt.millisecondsSinceEpoch,
        'messages': [for (final m in messages) m.toJson()],
      };

  factory Conversation.fromJson(Map<String, dynamic> j) => Conversation(
        id: j['id'] is String ? j['id'] as String : 'c0',
        title: j['title'] is String ? j['title'] as String : 'New chat',
        model: j['model'] is String ? j['model'] as String : null,
        createdAt: j['created_at'] is int
            ? DateTime.fromMillisecondsSinceEpoch(j['created_at'] as int)
            : null,
        messages: [
          for (final m in (j['messages'] as List? ?? const []))
            if (m is Map<String, dynamic>) ChatMessage.fromJson(m)
        ],
      );

  /// A title derived from the first user turn, trimmed for the sidebar.
  void titleFromFirstMessage() {
    for (final m in messages) {
      if (m.isUser && m.text.trim().isNotEmpty) {
        final t = m.text.trim().replaceAll('\n', ' ');
        title = t.length <= 40 ? t : '${t.substring(0, 40)}…';
        return;
      }
    }
  }
}
