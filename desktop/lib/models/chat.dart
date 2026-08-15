import 'dart:collection';
import 'dart:convert';

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

ChatMessage? chatHistoryAssistant(Conversation conversation, String prompt) {
  for (var index = conversation.messages.length - 2; index >= 0; index--) {
    final user = conversation.messages[index];
    final assistant = conversation.messages[index + 1];
    if (user.isUser &&
        user.text == prompt &&
        !assistant.isUser &&
        (assistant.text.isNotEmpty || assistant.receipt != null)) {
      return assistant;
    }
  }
  return null;
}

bool chatHasAdmittedPair(
    Conversation conversation, String prompt, Map<String, dynamic> event) {
  for (var index = 0; index + 1 < conversation.messages.length; index++) {
    final user = conversation.messages[index];
    final assistant = conversation.messages[index + 1];
    if (user.isUser &&
        user.text == prompt &&
        !assistant.isUser &&
        _chatMessageMatches(assistant, event)) {
      return true;
    }
  }
  return false;
}

bool _chatMessageMatches(ChatMessage assistant, Map<String, dynamic> event) {
  final text = event['text'] as String;
  final receipt = event['receipt'];
  if (receipt != null) {
    return jsonEncode(assistant.receipt) == jsonEncode(receipt);
  }
  return text.isNotEmpty && assistant.text.startsWith(text);
}

final _chatWindowsPath = RegExp(r'[A-Za-z]:[\\/]');
final _chatUncPath = RegExp(r'(?:\\\\|//)[^\\/\s]+[\\/][^\s]+');
final _chatPrivatePath = RegExp(r'(?:^|[\s=(\[{,:;])/(?!/)[^\s]+|/'
    r'(?:Users|home|private|tmp|var|etc|root|opt|mnt|srv|usr|bin|sbin|lib|'
    r'Applications|Volumes|dev|proc|sys|run)(?:/|$)');
final _chatFileUri = RegExp(r'(?<![A-Za-z0-9+.-])file:', caseSensitive: false);
final _chatSecretValue = RegExp(
    r'(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bsk-(?:live|proj|ant)[A-Za-z0-9_-]{10,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b)');
final _chatAssignedSecret = RegExp(
    r'\b(?:secret|password|passwd|api_key|access_key|token|credential)\s*[:=]\s*["\x27]?[A-Za-z0-9/+_-]{12,}',
    caseSensitive: false);
final _chatSecretKey = RegExp(r'^(?:api_keys?|access_tokens?|refresh_tokens?|'
    r'tokens?|passwords?|secrets?|credentials?|private_keys?|authorizations?|'
    r'cookies?|environments?|envs?|passwds?|access_keys?|.+_(?:api_keys?|'
    r'private_keys?|passwords?|secrets?|credentials?|tokens?))$');

bool safeChatLocalText(String value) {
  final decoded = _decodeChatPercent(value);
  return _safeChatForm(value) && _safeChatForm(decoded);
}

bool _safeChatForm(String value) =>
    !_chatWindowsPath.hasMatch(value) &&
    !_chatUncPath.hasMatch(value) &&
    !_chatPrivatePath.hasMatch(value) &&
    !_chatFileUri.hasMatch(value) &&
    !_chatSecretValue.hasMatch(value) &&
    !_chatAssignedSecret.hasMatch(value);

bool isChatLocalSecretKey(String key) => _chatSecretKey
    .hasMatch(_decodeChatPercent(key).toLowerCase().replaceAll('-', '_'));
bool safeChatLocalRef(String value) =>
    value.isNotEmpty && value.length <= 256 && !value.contains(':');

String _decodeChatPercent(String value) {
  final result = StringBuffer();
  for (var index = 0; index < value.length;) {
    if (value.codeUnitAt(index) != 0x25) {
      result.writeCharCode(value.codeUnitAt(index++));
      continue;
    }
    final next = index + 1 < value.length ? value.codeUnitAt(index + 1) : null;
    if (index + 2 >= value.length ||
        !_chatHex(next) ||
        !_chatHex(value.codeUnitAt(index + 2))) {
      result.write('%');
      index++;
      continue;
    }
    final start = index;
    while (index + 2 < value.length &&
        value.codeUnitAt(index) == 0x25 &&
        _chatHex(value.codeUnitAt(index + 1)) &&
        _chatHex(value.codeUnitAt(index + 2))) {
      index += 3;
    }
    try {
      result.write(Uri.decodeComponent(value.substring(start, index)));
    } catch (_) {
      throw ArgumentError('Invalid encoded local text');
    }
  }
  return result.toString();
}

bool _chatHex(int? value) =>
    value != null &&
    ((value >= 0x30 && value <= 0x39) ||
        (value >= 0x41 && value <= 0x46) ||
        (value >= 0x61 && value <= 0x66));
