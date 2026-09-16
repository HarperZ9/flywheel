part of 'chat.dart';

enum ChatTargetPrecision { exactOffset, clampedOffset, messageOnly, missing }

final class ChatTargetResolution {
  const ChatTargetResolution({
    required this.target,
    required this.precision,
    required this.messageIndex,
    required this.message,
    required this.offset,
  });

  final ChatTarget target;
  final ChatTargetPrecision precision;
  final int? messageIndex;
  final ChatMessage? message;
  final int? offset;
}

ChatTargetResolution resolveChatTarget(
  Conversation conversation,
  ChatTarget target,
) {
  if (conversation.id != target.conversationId) {
    return ChatTargetResolution(
      target: target,
      precision: ChatTargetPrecision.missing,
      messageIndex: null,
      message: null,
      offset: null,
    );
  }
  final index = conversation.messages
      .indexWhere((message) => message.id == target.messageId);
  if (index < 0) {
    return ChatTargetResolution(
      target: target,
      precision: ChatTargetPrecision.missing,
      messageIndex: null,
      message: null,
      offset: null,
    );
  }
  final message = conversation.messages[index];
  final offset = target.offset;
  if (offset == null) {
    return ChatTargetResolution(
      target: target,
      precision: ChatTargetPrecision.messageOnly,
      messageIndex: index,
      message: message,
      offset: null,
    );
  }
  final clamped = offset.clamp(0, message.text.length);
  return ChatTargetResolution(
    target: target,
    precision: clamped == offset
        ? ChatTargetPrecision.exactOffset
        : ChatTargetPrecision.clampedOffset,
    messageIndex: index,
    message: message,
    offset: clamped,
  );
}
