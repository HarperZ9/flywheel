part of 'chat_draft_store.dart';

Map<String, dynamic> _validAssistant(Object? value, String? attemptRef) {
  _require(value is Map<String, dynamic>);
  final assistant = value as Map<String, dynamic>;
  final expected = <String>{'role', 'text'};
  if (assistant.containsKey('id')) expected.add('id');
  if (assistant.containsKey('receipt')) expected.add('receipt');
  if (assistant.containsKey('attempt_ref')) expected.add('attempt_ref');
  _exactKeys(assistant, expected);
  _require(assistant['role'] == 'assistant' && assistant['text'] is String);
  _require(!assistant.containsKey('id') ||
      assistant['id'] is String && isChatMessageId(assistant['id'] as String));
  _require(!assistant.containsKey('receipt') ||
      assistant['receipt'] is Map<String, dynamic>);
  _require((assistant['text'] as String).isNotEmpty ||
      assistant.containsKey('receipt'));
  _require(assistant['attempt_ref'] == attemptRef);
  return assistant;
}
