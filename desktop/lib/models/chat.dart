import 'dart:collection';
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

import 'chat_reference.dart';
import 'evidence_state.dart';

export 'chat_local_safety.dart';
export 'chat_reference.dart';

part 'chat_resolution.dart';

enum PromptDisposition { accepted, retained }

typedef SubmitPrompt = Future<PromptDisposition> Function(String text);

class ChatMessage {
  factory ChatMessage({
    required String role,
    String? id,
    String text = '',
    bool streaming = false,
    Map<String, dynamic>? receipt,
    ReceiptState? receiptState,
    Map<String, dynamic>? run,
    String? attemptRef,
  }) {
    if (attemptRef != null && !isChatAttemptRef(attemptRef)) {
      throw ArgumentError('Invalid chat attempt reference');
    }
    if (id != null && !isChatMessageId(id)) {
      throw ArgumentError('Invalid chat message id');
    }
    final copy = receipt == null ? null : _immutableMap(receipt);
    return ChatMessage._(id ?? newChatMessageId(), role, text, streaming, copy,
        _effectiveReceiptState(copy != null, receiptState), run, attemptRef);
  }

  ChatMessage._(this.id, this.role, this.text, this.streaming, this._receipt,
      this.receiptState, this.run, this.attemptRef);

  final String id;
  final String role;
  String text;
  bool streaming;
  Map<String, dynamic>? _receipt;
  Map<String, dynamic>? get receipt => _receipt;
  ReceiptState receiptState;
  Map<String, dynamic>? run;
  final String? attemptRef;

  bool get isUser => role == 'user';
  Map<String, String> toWire() => {'role': role, 'content': text};

  void setReceipt(Map<String, dynamic>? value, {ReceiptState? state}) {
    _receipt = value == null ? null : _immutableMap(value);
    receiptState = _effectiveReceiptState(_receipt != null, state);
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'role': role,
        'text': text,
        if (attemptRef != null) 'attempt_ref': attemptRef,
        if (_receipt != null) 'receipt': _receipt,
      };

  factory ChatMessage.fromJson(Map<String, dynamic> json,
      {String? conversationId, int? position, Set<String>? usedIds}) {
    final rawReceipt = json['receipt'];
    final receipt = rawReceipt is Map<String, dynamic> ? rawReceipt : null;
    final malformedReceipt =
        json.containsKey('receipt') && rawReceipt != null && receipt == null;
    final id = _messageIdFromJson(json, conversationId, position, usedIds);
    final state = malformedReceipt ? ReceiptState.invalidResponse : null;
    return ChatMessage(
        id: id,
        role: json['role'] == 'user' ? 'user' : 'assistant',
        text: json['text'] is String ? json['text'] as String : '',
        receipt: receipt,
        receiptState: state,
        attemptRef: _attemptFromJson(json));
  }

  static String legacyId(String conversationId, int position) =>
      _legacyMessageId(conversationId, position);
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
    List<ChatBookmark>? bookmarks,
    this.notes = '',
    this.model,
    DateTime? createdAt,
    DateTime? updatedAt,
  })  : messages = messages ?? [],
        bookmarks = bookmarks ?? [],
        createdAt = createdAt ?? DateTime.now(),
        updatedAt = updatedAt ?? createdAt ?? DateTime.now();

  final String id;
  String title;
  final List<ChatMessage> messages;
  final List<ChatBookmark> bookmarks;
  String notes;
  String? model;
  final DateTime createdAt;

  DateTime updatedAt;

  bool get isEmpty =>
      messages.isEmpty && bookmarks.isEmpty && notes.trim().isEmpty;

  void touch() => updatedAt = DateTime.now();

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        if (model != null) 'model': model,
        if (notes.isNotEmpty) 'notes': notes,
        if (bookmarks.isNotEmpty)
          'bookmarks': [for (final bookmark in bookmarks) bookmark.toJson()],
        'created_at': createdAt.millisecondsSinceEpoch,
        'updated_at': updatedAt.millisecondsSinceEpoch,
        'messages': [for (final message in messages) message.toJson()],
      };

  factory Conversation.fromJson(Map<String, dynamic> json) {
    final id = json['id'] is String ? json['id'] as String : 'c0';
    final usedIds = <String>{};
    final messages = <ChatMessage>[];
    for (final raw in (json['messages'] as List? ?? const [])) {
      if (raw is Map<String, dynamic>) {
        messages.add(ChatMessage.fromJson(raw,
            conversationId: id, position: messages.length, usedIds: usedIds));
      }
    }
    return Conversation(
      id: id,
      title: json['title'] is String ? json['title'] as String : 'New chat',
      model: json['model'] is String ? json['model'] as String : null,
      notes: json['notes'] is String ? json['notes'] as String : '',
      bookmarks: [
        for (final raw in (json['bookmarks'] as List? ?? const []))
          if (ChatBookmark.fromJson(raw) case final bookmark?) bookmark
      ],
      createdAt: json['created_at'] is int
          ? DateTime.fromMillisecondsSinceEpoch(json['created_at'] as int)
          : null,
      updatedAt: json['updated_at'] is int
          ? DateTime.fromMillisecondsSinceEpoch(json['updated_at'] as int)
          : null,
      messages: messages,
    );
  }

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

ChatMessage? chatHistoryAssistant(
    Conversation conversation, String? attemptRef) {
  if (attemptRef == null) return null;
  for (var index = conversation.messages.length - 2; index >= 0; index--) {
    final user = conversation.messages[index];
    final assistant = conversation.messages[index + 1];
    if (user.isUser &&
        !assistant.isUser &&
        user.attemptRef == attemptRef &&
        assistant.attemptRef == attemptRef &&
        (assistant.text.isNotEmpty || assistant.receipt != null)) {
      return assistant;
    }
  }
  return null;
}

bool chatHasAdmittedPair(Conversation conversation, String? attemptRef) {
  if (attemptRef == null) return false;
  for (var index = 0; index + 1 < conversation.messages.length; index++) {
    final user = conversation.messages[index];
    final assistant = conversation.messages[index + 1];
    if (user.isUser &&
        !assistant.isUser &&
        user.attemptRef == attemptRef &&
        assistant.attemptRef == attemptRef) {
      return true;
    }
  }
  return false;
}

final _chatAttemptRef = RegExp(r'^att_[0-9a-f]{32}$');

bool isChatAttemptRef(String value) => _chatAttemptRef.hasMatch(value);

String newChatAttemptRef() {
  return 'att_${_randomHex128()}';
}

String newChatMessageId() {
  return 'msg_${_randomHex128()}';
}

String _randomHex128() {
  final random = Random.secure();
  return List.generate(16, (_) => random.nextInt(256))
      .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
      .join();
}

String? _attemptFromJson(Map<String, dynamic> json) {
  if (!json.containsKey('attempt_ref')) return null;
  final value = json['attempt_ref'];
  if (value is! String || !isChatAttemptRef(value)) {
    throw const FormatException('Invalid chat attempt reference');
  }
  return value;
}

String _messageIdFromJson(Map<String, dynamic> json, String? conversationId,
    int? position, Set<String>? usedIds) {
  final raw = json['id'];
  final fallback = conversationId != null && position != null
      ? _legacyMessageId(conversationId, position)
      : newChatMessageId();
  var candidate = raw is String && isChatMessageId(raw) ? raw : fallback;
  if (usedIds == null || usedIds.add(candidate)) return candidate;
  candidate = fallback;
  var collision = 0;
  while (!usedIds.add(candidate)) {
    collision++;
    candidate = _legacyMessageId(
        conversationId ?? 'conversation', position ?? 0,
        collision: collision);
  }
  return candidate;
}

String _legacyMessageId(String conversationId, int position,
    {int collision = 0}) {
  if (position < 0 || collision < 0) {
    throw ArgumentError('Invalid legacy message position');
  }
  final digest = sha256
      .convert(utf8.encode(
          'flywheel.desktop-chat-message/v1\x00$conversationId\x00$position\x00$collision'))
      .toString();
  return 'msg_${digest.substring(0, 32)}';
}
