import 'agent_trace_record.dart';

enum CaptionKind {
  providerReasoning('provider_reasoning'),
  providerSummary('provider_summary'),
  generatedSummary('generated_summary'),
  assistantOutput('assistant_output'),
  toolActivity('tool_activity'),
  inferenceActivity('inference_activity'),
  progress('progress');

  final String wire;
  const CaptionKind(this.wire);
}

/// A display projection of an authenticated original, never reconstructed thought.
final class AgentCaption {
  final CaptionKind kind;
  final String text, label, source;
  final TraceRecord record;
  final DateTime receivedAt;
  DateTime? get eventTimestamp => null;
  const AgentCaption._(this.kind, this.text, this.label, this.source,
      this.record, this.receivedAt);

  static AgentCaption? fromRecord(TraceRecord record, DateTime receivedAt) {
    final payload = record.payload;
    AgentCaption caption(
            CaptionKind kind, String text, String label, String source) =>
        AgentCaption._(kind, text, label, source, record, receivedAt.toUtc());
    if (record.kind == 'ledger') {
      final text = payload['content'],
          kind = payload['kind'],
          meta = payload['meta'];
      if (text is! String || meta is! Map || payload['seq'] is! int) {
        return null;
      }
      switch (kind) {
        case 'assistant':
          return caption(CaptionKind.assistantOutput, text, 'Assistant output',
              'ledger.content');
        case 'model_inference':
          return _inferenceCaption(record, receivedAt, meta);
        case 'tool_call':
          return caption(CaptionKind.toolActivity, text, 'Tool call recorded',
              'ledger.content · after execution');
        case 'tool_result':
          final ok = meta['ok'];
          if (ok is! bool || meta['tool'] is! String) return null;
          return caption(
              CaptionKind.toolActivity,
              text,
              'Tool result · ${ok ? 'reported success' : 'reported failure'}',
              'ledger.content');
      }
    }
    if (record.kind == 'progress' && payload['type'] == 'budget') {
      final step = payload['step'],
          max = payload['max_steps'],
          remaining = payload['remaining'];
      if (step is! int ||
          max is! int ||
          remaining is! int ||
          step < 1 ||
          max < step ||
          remaining < 0 ||
          remaining > max) {
        return null;
      }
      return caption(
          CaptionKind.progress,
          'Step $step of $max · $remaining remaining',
          'Step budget',
          'loop progress · budget');
    }
    if (record.kind == 'result' && payload['final'] is String) {
      return caption(CaptionKind.assistantOutput, payload['final'] as String,
          'Final output', 'router result.final');
    }
    // Provider channels require their own agreed schema. Never promote fields
    // named thinking/reasoning/summary, signatures, or opaque blocks heuristically.
    // Assistant/tool progress mirrors are omitted: their full originals above
    // are committed to the ledger before local_loop emits the short projection.
    return null;
  }
}

AgentCaption? _inferenceCaption(
    TraceRecord record, DateTime receivedAt, Map meta) {
  final schema = meta['schema'],
      ordinal = meta['ordinal'],
      binding = meta['binding_sha256'],
      endpoint = meta['endpoint'],
      model = meta['model_id'],
      phase = meta['phase'],
      observed = meta['observed_at_utc'],
      elapsed = meta['elapsed_ms'],
      reason = meta['reason'];
  final safeRef = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,159}$');
  final reasonCode = RegExp(r'^[A-Z][A-Z0-9_]{0,63}$');
  if (schema != 'flywheel.gateway-agent-inference/v1' ||
      ordinal is! int ||
      ordinal < 0 ||
      binding is! String ||
      !RegExp(r'^[0-9a-f]{64}$').hasMatch(binding) ||
      endpoint is! String ||
      !safeRef.hasMatch(endpoint) ||
      model is! String ||
      !safeRef.hasMatch(model) ||
      phase is! String ||
      !const {'started', 'response_received', 'failed'}.contains(phase) ||
      observed is! String ||
      !RegExp(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T').hasMatch(observed) ||
      elapsed is! int ||
      elapsed < 0) {
    return null;
  }
  if (reason != null &&
      (phase != 'failed' ||
          reason is! String ||
          !reasonCode.hasMatch(reason))) {
    return null;
  }
  if (phase == 'failed' && reason == null) {
    return null;
  }
  final phaseLabel = switch (phase) {
    'started' => 'started',
    'response_received' => 'response received',
    'failed' => 'failed',
    _ => phase,
  };
  final reasonText = reason == null ? '' : ' · $reason';
  return AgentCaption._(
      CaptionKind.inferenceActivity,
      'Inference call $ordinal $phaseLabel · endpoint $endpoint · model $model · ${elapsed}ms$reasonText',
      'Inference $phaseLabel',
      'agent inference lifecycle',
      record,
      receivedAt.toUtc());
}
