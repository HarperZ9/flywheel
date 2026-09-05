// action_witness_line.dart -- a finished run's own byte-witness chain, rechecked
// here, on the surface where the run finished.
//
// The engine witnesses the exact bytes of every action it takes and links the
// records into one chain per run. The run result carries that chain, so this
// needs no paste, no export, and no second call: every link is recomputed in
// Dart from the result already in hand.
//
// The records travel and the bytes do not, so the ordinary honest answer is
// UNVERIFIABLE with the links intact, and this says that in those words. Three
// two other states are named rather than hidden: a chain too large to travel,
// and a result that handed over no chain at all. Silence on either would read
// as "checked and fine".

import 'package:flutter/material.dart';

import '../models/byte_witness.dart';
import '../models/byte_witness_chain.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ActionWitnessLine extends StatelessWidget {
  /// A finished run's result map, as the gateway returned it.
  final Map<String, dynamic> run;
  const ActionWitnessLine({super.key, required this.run});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final records = byteWitnessRecordsIn(run);
    return Padding(
      padding: const EdgeInsets.only(top: FwLayout.s3),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('action witness'),
        const SizedBox(height: FwLayout.s2),
        if (records != null)
          _checked(t, verifyByteWitnessChain(records))
        else
          HonestNull(_absent()),
      ]),
    );
  }

  /// What this run says about a chain it did not hand over. Never silence.
  String _absent() {
    final omitted = byteWitnessOmissionIn(run);
    if (omitted != null) {
      return 'This run witnessed its actions and left the records behind, so '
          'there is nothing here to recheck. $omitted';
    }
    // The engine leaves the key out for a run that took no witnessed action
    // and for a run that predates the chain alike, so this does not guess
    // which. Either way nothing was checked here.
    return 'This run handed over no witness chain. Nothing here was checked, '
        'and nothing here is a claim that it was.';
  }

  Widget _checked(FwTokens t, ByteWitnessChainResult r) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        switch (r.verdict) {
          ByteWitnessVerdict.match =>
            const VerdictPill('reproduced', status: 'verified'),
          ByteWitnessVerdict.tampered =>
            const VerdictPill('tampered', status: 'drift'),
          ByteWitnessVerdict.unverifiable =>
            const VerdictPill('unverifiable', status: 'unverifiable'),
        },
        const SizedBox(width: FwLayout.s2),
        Flexible(
          child: Text(
              '${r.checked} records checked'
              '${r.brokenAt == null ? '' : ', broke at record ${r.brokenAt}'}',
              style: fwMono(t, size: 11.5, color: t.inkSoft)),
        ),
      ]),
      const SizedBox(height: FwLayout.s2),
      Text(r.detail, style: fwMono(t, size: 10.5, color: t.inkFaint)),
      if (r.head != null) ...[
        const SizedBox(height: FwLayout.s2),
        HashText('head', r.head!),
      ],
      const SizedBox(height: FwLayout.s2),
      Text('does not prove', style: fwMono(t, size: 11, color: t.inkFaint)),
      const SizedBox(height: FwLayout.s1),
      for (final line in r.doesNotProve)
        Padding(
          padding: const EdgeInsets.only(bottom: FwLayout.s1),
          child: Text('· $line',
              style: TextStyle(fontSize: 11.5, height: 1.4, color: t.inkMuted)),
        ),
    ]);
  }
}
