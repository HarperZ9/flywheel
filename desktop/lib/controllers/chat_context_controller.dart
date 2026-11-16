import 'dart:async';

import '../client/gateway_client.dart';
import '../models/context_memory.dart';
import '../services/chat_draft_store.dart';

typedef ChatContextCurrent = bool Function();

final class ChatContextController {
  const ChatContextController(this.client,
      {this.deadline = const Duration(seconds: 5)});

  final GatewayClient client;
  final Duration deadline;

  Future<ChatContextOutcome> prepare({
    required ChatDraft draft,
    required ChatContextCurrent isCurrent,
  }) async {
    final stopwatch = Stopwatch()..start();
    try {
      final status = ContextMemoryStatus.fromJson(
          await _within(() => client.contextMemoryStatus(), stopwatch));
      if (status.invalidResponse) {
        return ChatContextOutcome.statusFailure(
            'Context status response was invalid.');
      }
      if (!status.configured) return ChatContextOutcome.notConfigured(status.message);
      if (!isCurrent()) return ChatContextOutcome.cancelled();

      final preflight = await _preflight(status, draft, stopwatch);
      if (!isCurrent()) return ChatContextOutcome.cancelled();
      final capture = await _capture(status, draft, stopwatch);
      return ChatContextOutcome(
          configured: true, preflight: preflight, capture: capture);
    } on TimeoutException {
      return ChatContextOutcome.statusFailure('Canon context timed out.');
    } on Object catch (error) {
      return ChatContextOutcome.statusFailure(
          'Canon context failed: ${_errorMessage(error)}.');
    }
  }

  Future<ContextMemoryPreflightResult> _preflight(
      ContextMemoryStatus status, ChatDraft draft, Stopwatch stopwatch) async {
    try {
      final raw = await _within(
          () => client.contextMemoryPreflight(
              projectRef: status.projectRef,
              configGeneration: status.destinationBinding!.configGeneration,
              canonStoreId: status.destinationBinding!.canonStoreId,
              query: draft.text,
              topK: 10,
              includePendingExtraction: true),
          stopwatch);
      final parsed = ContextMemoryPreflight.fromJson(raw, status.projectRef,
          currentNativeId: draft.attemptRef ?? '');
      return parsed.invalidResponse
          ? ContextMemoryPreflightResult.failure(parsed.message)
          : ContextMemoryPreflightResult.value(parsed);
    } on TimeoutException {
      return ContextMemoryPreflightResult.failure('Context search timed out.');
    } on Object catch (error) {
      return ContextMemoryPreflightResult.failure(
          'Context search failed: ${_errorMessage(error)}.');
    }
  }

  Future<ContextMemoryCaptureResult> _capture(
      ContextMemoryStatus status, ChatDraft draft, Stopwatch stopwatch) async {
    try {
      final raw = await _within(
          () => client.contextMemoryCapture(
              projectRef: status.projectRef,
              configGeneration: status.destinationBinding!.configGeneration,
              canonStoreId: status.destinationBinding!.canonStoreId,
              event: contextMemoryCaptureEvent(draft)),
          stopwatch);
      final parsed = ContextMemoryCapture.fromJson(raw, status.projectRef);
      return parsed.success
          ? ContextMemoryCaptureResult.value(parsed)
          : ContextMemoryCaptureResult.failure(parsed.message);
    } on TimeoutException {
      return ContextMemoryCaptureResult.failure(
          'Canon capture timed out; completion unknown.');
    } on Object catch (error) {
      return ContextMemoryCaptureResult.failure(
          'Canon capture failed: ${_errorMessage(error)}.');
    }
  }

  Future<T> _within<T>(Future<T> Function() start, Stopwatch stopwatch) {
    final remaining = deadline - stopwatch.elapsed;
    if (remaining <= Duration.zero) {
      throw TimeoutException('Canon context timed out');
    }
    return start().timeout(remaining);
  }
}

Map<String, Object?> contextMemoryCaptureEvent(ChatDraft draft) =>
    Map.unmodifiable({
      'event_id': draft.attemptRef,
      'attempt_ref': draft.attemptRef,
      'source_app': 'flywheel-desktop',
      'source_surface': 'agent-view-text-chat',
      'event_kind': 'chat_submission_attempt',
      'capture_method': 'desktop-agent-view-text-submit',
      'native_id': draft.attemptRef,
      'conversation_ref': draft.conversationRef,
      'session_ref': 'desktop-chat-${draft.conversationRef}',
      'session_id': 'desktop-chat-${draft.conversationRef}',
      'role': 'user',
      'message_text': draft.text,
      'text_sha256': draft.textSha256,
    });

final class ChatContextOutcome {
  const ChatContextOutcome({
    required this.configured,
    this.cancelled = false,
    this.pending = false,
    this.statusMessage = '',
    this.preflight,
    this.capture,
  });

  final bool configured, cancelled, pending;
  final String statusMessage;
  final ContextMemoryPreflightResult? preflight;
  final ContextMemoryCaptureResult? capture;

  factory ChatContextOutcome.pending() =>
      const ChatContextOutcome(configured: false, pending: true);
  factory ChatContextOutcome.cancelled() =>
      const ChatContextOutcome(configured: false, cancelled: true);
  factory ChatContextOutcome.notConfigured([String message = 'not configured']) =>
      ChatContextOutcome(
          configured: false, statusMessage: 'Canon context $message.');
  factory ChatContextOutcome.statusFailure(String message) =>
      ChatContextOutcome(configured: false, statusMessage: message);

  String? get providerContext => preflight?.value?.providerContext;
  int get referenceCount => preflight?.value?.hits.length ?? 0;

  String get displayText {
    if (pending) return 'Canon context: checking.';
    if (statusMessage.isNotEmpty) return statusMessage;
    final parts = <String>[];
    final search = preflight;
    if (search?.message case final value?) {
      parts.add(search!.value == null ? value : 'Canon context: $value');
    }
    if (capture?.message case final value?) parts.add(value);
    return parts.isEmpty ? '' : parts.join('; ');
  }
}

final class ContextMemoryPreflightResult {
  const ContextMemoryPreflightResult._(this.value, this.message);
  factory ContextMemoryPreflightResult.value(ContextMemoryPreflight value) =>
      ContextMemoryPreflightResult._(value, value.message);
  factory ContextMemoryPreflightResult.failure(String message) =>
      ContextMemoryPreflightResult._(null, message);

  final ContextMemoryPreflight? value;
  final String message;
}

final class ContextMemoryCaptureResult {
  const ContextMemoryCaptureResult._(this.value, this.message);
  factory ContextMemoryCaptureResult.value(ContextMemoryCapture value) =>
      ContextMemoryCaptureResult._(value, value.message);
  factory ContextMemoryCaptureResult.failure(String message) =>
      ContextMemoryCaptureResult._(null, message);

  final ContextMemoryCapture? value;
  final String message;
}

String _errorMessage(Object error) =>
    error is GatewayException ? error.message : 'request failed';
