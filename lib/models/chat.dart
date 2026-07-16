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
