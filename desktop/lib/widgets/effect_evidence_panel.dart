import 'dart:convert';

import 'package:flutter/material.dart';
import '../models/agent_trace_record.dart';
import '../models/canonical_json.dart';
import '../models/effect_evidence.dart';
import '../models/effect_source_summary.dart';
import '../theme/flywheel_theme.dart';

class EffectEvidencePanel extends StatelessWidget {
  final EffectEvidence evidence;
  final List<TraceRecord> records;
  final void Function(int sequence) onSelect;
  const EffectEvidencePanel(
      {super.key,
      required this.evidence,
      required this.records,
      required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final t = context.fw, text = Theme.of(context).textTheme.bodyMedium;
    final count = evidence.knownObservationCount;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(
          count == 0
              ? 'Effect evidence: no retained observations surfaced in this accepted prefix.'
              : 'Effect evidence: $count retained observation${count == 1 ? '' : 's'} surfaced'
                  '${evidence.knownObservationsOmitted == 0 ? '' : ', ${evidence.knownObservationsOmitted} omitted by cap'}.',
          style: text),
      Text(
          'Terminal state ${evidence.basis.terminalState}; basis event '
          '${evidence.basis.terminalBasisEventType}.',
          style: text?.copyWith(color: t.inkMuted)),
      Text('Unknown scope: ${_unknownSummary(evidence.unknownEffectScope)}',
          style: text?.copyWith(color: t.inkMuted)),
      SelectableText('Raw unknown scope: ${evidence.unknownEffectScope.join(', ')}',
          style: fwMono(t, size: 11)),
      Text(
          'Witness ${evidence.actionWitness.status}; tool receipts '
          '${evidence.toolCallReceipts.status}. Source values appear only after '
          'the private trace read checks the record bytes.',
          style: text?.copyWith(color: t.inkMuted)),
      for (var i = 0; i < evidence.knownObservations.length; i++)
        _SourceValue(
            label: 'Observation ${i + 1}',
            source: _SourceRef.observation(evidence.knownObservations[i]),
            records: records,
            onSelect: onSelect),
      _SourceValue(
          label: 'Action witness summary',
          source: _SourceRef.summary(evidence.actionWitness),
          records: records,
          onSelect: onSelect),
      _SourceValue(
          label: 'Tool receipt summary',
          source: _SourceRef.summary(evidence.toolCallReceipts),
          records: records,
          onSelect: onSelect),
    ]);
  }
}

class _SourceValue extends StatelessWidget {
  final String label;
  final _SourceRef? source;
  final List<TraceRecord> records;
  final void Function(int sequence) onSelect;
  const _SourceValue(
      {required this.label,
      required this.source,
      required this.records,
      required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final t = context.fw, text = Theme.of(context).textTheme.bodyMedium;
    final source = this.source;
    if (source == null) return const SizedBox.shrink();
    final record = _loaded(records, source.sequence);
    if (record == null) {
      return Padding(
          padding: const EdgeInsets.only(top: FwLayout.s1),
          child: Text(
              '$label: source record ${source.sequence + 1} is not loaded.',
              style: text));
    }
    final value = _sourceValue(record, source);
    final sourceText = value == null ? null : _sourceText(value);
    return Padding(
        padding: const EdgeInsets.only(top: FwLayout.s1),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
            Text(
                value == null
                    ? '$label: source record did not match this descriptor.'
                    : '$label: record hash matches descriptor; '
                        '${source.pointer} source value hash matches.',
                style: text),
            TextButton(
                onPressed: () => onSelect(source.sequence),
                child: const Text('Show source record')),
          ]),
          if (sourceText != null)
            SelectableText(sourceText, style: fwMono(t, size: 11)),
        ]));
  }
}

final class _SourceRef {
  final int sequence;
  final String recordSha256, recordKind, pointer, valueSha256;
  const _SourceRef(
      this.sequence, this.recordSha256, this.recordKind, this.pointer,
      this.valueSha256);
  factory _SourceRef.observation(EffectObservation observation) => _SourceRef(
      observation.traceSequence,
      observation.recordSha256,
      observation.recordKind,
      observation.jsonPointer,
      observation.valueSha256);
  static _SourceRef? summary(EffectSourceSummary summary) {
    if (summary.traceSequence == null ||
        summary.recordSha256 == null ||
        summary.recordKind == null ||
        summary.jsonPointer == null ||
        summary.valueSha256 == null) {
      return null;
    }
    return _SourceRef(summary.traceSequence!, summary.recordSha256!,
        summary.recordKind!, summary.jsonPointer!, summary.valueSha256!);
  }
}

TraceRecord? _loaded(List<TraceRecord> records, int sequence) {
  for (final record in records) {
    if (record.sequence == sequence) return record;
  }
  return null;
}

Object? _sourceValue(TraceRecord record, _SourceRef source) {
  if (record.sequence != source.sequence ||
      record.recordSha256 != source.recordSha256 ||
      record.kind != source.recordKind) {
    return null;
  }
  final value = _pointerValue({'payload': record.payload}, source.pointer);
  if (value == null) return null;
  try {
    return canonicalJsonSha256(value) == source.valueSha256 ? value : null;
  } on Object {
    return null;
  }
}

Object? _pointerValue(Object? root, String pointer) {
  if (pointer.isEmpty) return root;
  if (!pointer.startsWith('/')) return null;
  var current = root;
  for (final raw in pointer.substring(1).split('/')) {
    final token = raw.replaceAll('~1', '/').replaceAll('~0', '~');
    if (current is Map && current.containsKey(token)) {
      current = current[token];
    } else if (current is List) {
      final index = int.tryParse(token);
      if (index == null || index < 0 || index >= current.length) return null;
      current = current[index];
    } else {
      return null;
    }
  }
  return current;
}

String _sourceText(Object? value) {
  const limit = 4096;
  try {
    final text = jsonEncode(value);
    final shown = text.length <= limit ? text : text.substring(0, limit);
    return text.length <= limit
        ? 'Private source value preview (${text.length} chars shown):\n$shown'
        : 'Private source value preview (first $limit of ${text.length} chars; '
            'use Show source record for full canonical context):\n$shown';
  } on Object {
    final text = '$value';
    final shown = text.length <= limit ? text : text.substring(0, limit);
    return text.length <= limit
        ? 'Private source value preview (${text.length} chars shown):\n$shown'
        : 'Private source value preview (first $limit of ${text.length} chars; '
            'use Show source record for full canonical context):\n$shown';
  }
}

String _unknownSummary(List<String> codes) {
  final labels = <String>[
    if (codes.contains('NOT_ROLLBACK')) 'no rollback proof',
    if (codes.contains('NOT_EFFECT_ABSENCE')) 'no effect-absence proof',
    if (codes.contains('NOT_CURRENT_FILESYSTEM_STATE')) 'not current state',
    if (codes.contains('UNRECORDED_ACTIONS_NOT_EXCLUDED'))
      'unrecorded actions remain possible',
    if (codes.contains('TOOLS_WITHOUT_POST_EFFECT_FINGERPRINTS_REMAIN_UNKNOWN'))
      'unfingerprinted tools remain unknown',
    if (codes.contains('EFFECTS_AFTER_TRACE_HEAD_REMAIN_UNKNOWN'))
      'later effects remain unknown',
  ];
  return labels.join('; ');
}
