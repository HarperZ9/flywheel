// lane_policy_review.dart - what a lane.call approval authorizes, on the
// approval sheet.
//
// The engine builds this block (harness/lane_tier_gate.lane_policy_review,
// POLICY-DECISION C-13): the tier the tool needs and the tier the call asks
// for, its effect, what the engine forces or drops, and the arguments the
// lane child receives. The sheet shows it as sent; nothing is recomputed.

import 'dart:convert';

import 'package:flutter/material.dart';

String _plain(Object? value) =>
    value is String ? value : const JsonEncoder().convert(value);

/// The review lines for [policy], in the order the owner reads them.
List<String> lanePolicyLines(Map<String, Object?> policy) {
  final forced = policy['forced_arguments'];
  final dropped = policy['dropped_arguments'];
  return [
    'Tier: needs ${_plain(policy['required_tier'])}, '
        'asks ${_plain(policy['requested_tier'])}',
    if ('${policy['effect'] ?? ''}'.isNotEmpty)
      'Effect: ${_plain(policy['effect'])}',
    if ('${policy['reason'] ?? ''}'.isNotEmpty)
      'Why: ${_plain(policy['reason'])}',
    if (policy['binds_key'] == true) 'Binds a key: yes, so the call is T2',
    if (forced is Map && forced.isNotEmpty) 'Engine sets: ${_plain(forced)}',
    if (dropped is List && dropped.isNotEmpty)
      'Engine drops: ${dropped.join(', ')}',
    'Lane receives: ${_plain(policy['arguments'] ?? const {})}',
  ];
}

class LanePolicyReview extends StatelessWidget {
  final Map<String, Object?> policy;
  const LanePolicyReview({super.key, required this.policy});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 6, bottom: 6),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Lane tool policy',
              style: TextStyle(fontWeight: FontWeight.w700)),
          for (final line in lanePolicyLines(policy))
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: SelectableText(line, maxLines: 6),
            ),
        ]),
      );
}
