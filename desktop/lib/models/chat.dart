import 'dart:collection';

import 'evidence_state.dart';

enum PromptDisposition { accepted, retained }

typedef SubmitPrompt = Future<PromptDisposition> Function(String text);

class ChatMessage {
  factory ChatMessage({
    required String role,
    String text = '',
    bool streaming = false,
    Map<String, dynamic>? receipt,
    ReceiptState? receiptState,
    Map<String, dynamic>? run,
  }) {
    final copy = receipt == null ? null : _immutableMap(receipt);
    return ChatMessage._(role, text, streaming, copy,
        _effectiveReceiptState(copy != null, receiptState), run);
  }

  ChatMessage._(this.role, this.text, this.streaming, this._receipt,
      this.receiptState, this.run);

  final String role;
  String text;
  bool streaming;
  Map<String, dynamic>? _receipt;
  Map<String, dynamic>? get receipt => _receipt;
  ReceiptState receiptState;
  Map<String, dynamic>? run;

  bool get isUser => role == 'user';
  Map<String, String> toWire() => {'role': role, 'content': text};

  void setReceipt(Map<String, dynamic>? value, {ReceiptState? state}) {
    _receipt = value == null ? null : _immutableMap(value);
    receiptState = _effectiveReceiptState(_receipt != null, state);
  }

  Map<String, dynamic> toJson() => {
        'role': role,
        'text': text,
        if (_receipt != null) 'receipt': _receipt,
      };

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    final rawReceipt = json['receipt'];
    final receipt = rawReceipt is Map<String, dynamic> ? rawReceipt : null;
    final malformedReceipt =
        json.containsKey('receipt') && rawReceipt != null && receipt == null;
    final state = malformedReceipt ? ReceiptState.invalidResponse : null;
    return ChatMessage(
        role: json['role'] == 'user' ? 'user' : 'assistant',
        text: json['text'] is String ? json['text'] as String : '',
        receipt: receipt,
        receiptState: state);
  }
}

ReceiptState _effectiveReceiptState(bool present, ReceiptState? state) {
  if (!present) {
    return state == null || state == ReceiptState.missing
        ? ReceiptState.missing
        : ReceiptState.invalidResponse;
  }
  return switch (state) {
    null => ReceiptState.presentUnchecked,
    ReceiptState.presentUnchecked ||
    ReceiptState.match ||
    ReceiptState.drift ||
    ReceiptState.tampered ||
    ReceiptState.unverifiable =>
      state,
    _ => ReceiptState.invalidResponse,
  };
}

Map<String, dynamic> _immutableMap(Map<String, dynamic> source) {
  final result = SplayTreeMap<String, dynamic>();
  for (final entry in source.entries) {
    result[entry.key] = _immutableJson(entry.value);
  }
  return Map.unmodifiable(result);
}

dynamic _immutableJson(Object? value) {
  if (value == null || value is String || value is bool) return value;
  if (value is num && value.isFinite) return value;
  if (value is List) return List.unmodifiable(value.map(_immutableJson));
  if (value is Map<String, dynamic>) return _immutableMap(value);
  throw ArgumentError('Receipt contains unsupported local data');
}

class Conversation {
  Conversation({
    required this.id,
    this.title = 'New chat',
    List<ChatMessage>? messages,
    this.model,
    DateTime? createdAt,
  })  : messages = messages ?? [],
        createdAt = createdAt ?? DateTime.now();

  final String id;
  String title;
  final List<ChatMessage> messages;
  String? model;
  final DateTime createdAt;

  bool get isEmpty => messages.isEmpty;

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        if (model != null) 'model': model,
        'created_at': createdAt.millisecondsSinceEpoch,
        'messages': [for (final message in messages) message.toJson()],
      };

  factory Conversation.fromJson(Map<String, dynamic> json) => Conversation(
        id: json['id'] is String ? json['id'] as String : 'c0',
        title: json['title'] is String ? json['title'] as String : 'New chat',
        model: json['model'] is String ? json['model'] as String : null,
        createdAt: json['created_at'] is int
            ? DateTime.fromMillisecondsSinceEpoch(json['created_at'] as int)
            : null,
        messages: [
          for (final message in (json['messages'] as List? ?? const []))
            if (message is Map<String, dynamic>) ChatMessage.fromJson(message)
        ],
      );

  void titleFromFirstMessage() {
    for (final message in messages) {
      if (message.isUser && message.text.trim().isNotEmpty) {
        final text = message.text.trim().replaceAll('\n', ' ');
        title = text.length <= 40 ? text : '${text.substring(0, 40)}…';
        return;
      }
    }
  }
}
