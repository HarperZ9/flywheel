// companion_receipt_strip.dart -- the companion answer's own receipt, rendered.
//
// The answer card used to pass this object to HashText, which takes a string,
// so the model declared the field as one and every real answer threw on parse.
// The engine sends a selection receipt: how the answer was chosen, how many
// candidates it cost, and what the oracle said. That is worth rendering, and it
// is the only place the operator can see whether the effort dial they set was
// actually spent.
//
// Every field is optional on purpose. A receipt from an older engine, or from a
// path that fills fewer fields, degrades to the rows it has rather than
// throwing or showing a zero it never measured.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class CompanionReceiptStrip extends StatelessWidget {
  final Map<String, dynamic>? receipt;
  const CompanionReceiptStrip(this.receipt, {super.key});

  static String? _text(Map<String, dynamic> m, String key) {
    final v = m[key];
    return v is String && v.isNotEmpty ? v : null;
  }

  static int? _int(Map<String, dynamic> m, String key) {
    final v = m[key];
    if (v is int) return v;
    if (v is num) return v.toInt();
    return null;
  }

  /// A confidence is a ratio, and a ratio printed at full float width reads as
  /// precision the measurement does not have.
  static String? _ratio(Map<String, dynamic> m, String key) {
    final v = m[key];
    return v is num ? v.toStringAsFixed(2) : null;
  }

  /// The dial, and what it actually bought. `applied` is the engine's own word
  /// for which dimension the run enforced, so it is read rather than guessed.
  static String? _effortLine(Map<String, dynamic>? effort) {
    if (effort == null) return null;
    final name = _text(effort, 'name');
    if (name == null) return null;
    final applied = _text(effort, 'applied');
    if (applied == 'candidates') {
      final spent = _int(effort, 'candidates_generated');
      final ceiling = _int(effort, 'max_n_applied');
      if (spent == null || ceiling == null) return name;
      return '$name · $spent of $ceiling candidates';
    }
    if (applied == 'none') {
      final why = _text(effort, 'reason');
      return why == null ? '$name · nothing spent' : '$name · $why';
    }
    // An engine that stamped a dimension this build does not know about. Show
    // the level and the word it used rather than inventing a reading for it.
    return applied == null ? name : '$name · $applied';
  }

  @override
  Widget build(BuildContext context) {
    final r = receipt;
    if (r == null || r.isEmpty) return const SizedBox.shrink();
    final t = context.fw;

    final effort = r['effort'] is Map
        ? Map<String, dynamic>.from(r['effort'] as Map)
        : null;
    // Short scalars share a wrapping row. The effort line does not: its reason
    // is a sentence, and a sentence in a min-width Row overflows the card
    // rather than wrapping inside it.
    final rows = <(String, String)>[
      if (_text(r, 'method') != null) ('method', _text(r, 'method')!),
      if (_int(r, 'candidates_used') != null)
        ('candidates', '${_int(r, 'candidates_used')}'),
      if (_ratio(r, 'confidence') != null)
        ('confidence', _ratio(r, 'confidence')!),
    ];
    final battery = _text(r, 'battery_hash');
    final effortLine = _effortLine(effort);
    final reason = _text(r, 'reason');
    if (rows.isEmpty &&
        battery == null &&
        effortLine == null &&
        reason == null) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (rows.isNotEmpty || battery != null)
          Wrap(
            spacing: FwLayout.s4,
            runSpacing: FwLayout.s1,
            children: [
              for (final (label, value) in rows)
                _Pair(label: label, value: value),
              if (battery != null)
                HashText('battery', battery, keep: 16, linkToReceipts: true),
            ],
          ),
        if (effortLine != null) ...[
          const SizedBox(height: FwLayout.s1),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('effort', style: fwMono(t, size: 11.5, color: t.inkFaint)),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: SelectableText(effortLine,
                    style: fwMono(t, size: 12, weight: FontWeight.w600)
                        .copyWith(height: 1.4)),
              ),
            ],
          ),
        ],
        if (reason != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text(reason,
              style: fwMono(t, size: 11.5, color: t.inkMuted)
                  .copyWith(height: 1.4)),
        ],
      ],
    );
  }
}

/// One short label/value pair. Flexible on the value, because a method name
/// from a future engine is not bounded by what this build knows about.
class _Pair extends StatelessWidget {
  final String label;
  final String value;
  const _Pair({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: fwMono(t, size: 11.5, color: t.inkFaint)),
        const SizedBox(width: FwLayout.s2),
        Flexible(
          child: SelectableText(value,
              maxLines: 1, style: fwMono(t, size: 12, weight: FontWeight.w600)),
        ),
      ],
    );
  }
}
