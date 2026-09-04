// action_witness_panel.dart -- check a run's byte-witness chain on this device.
//
// The engine witnesses the exact bytes of every action it takes and links the
// records into one chain per run. This panel takes that log and rechecks it
// here: every link recomputed in Dart, nothing taken on the gateway's word.
//
// The records travel and the bytes do not, so the ordinary honest answer is
// UNVERIFIABLE with the links intact. The panel says that in those words. It
// never renders a linked chain as verified, because a chain of digests proves
// the order and integrity of the records and says nothing about content nobody
// produced. Presentation only; the truth is in lib/models/byte_witness*.dart.

import 'package:flutter/material.dart';

import '../models/byte_witness.dart';
import '../models/byte_witness_chain.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ActionWitnessPanel extends StatefulWidget {
  const ActionWitnessPanel({super.key});

  @override
  State<ActionWitnessPanel> createState() => _ActionWitnessPanelState();
}

class _ActionWitnessPanelState extends State<ActionWitnessPanel> {
  final _ctrl = TextEditingController();
  ByteWitnessChainResult? _result;
  bool _unreadable = false;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _check() {
    final records = readByteWitnessLog(_ctrl.text);
    setState(() {
      _unreadable = records == null;
      _result = records == null ? null : verifyByteWitnessChain(records);
    });
  }

  void _clear() {
    _ctrl.clear();
    setState(() {
      _result = null;
      _unreadable = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('action witness'),
        const SizedBox(height: FwLayout.s2),
        Text(
          'Every action the engine takes leaves two records: the bytes that '
          'went in and the bytes that came back, linked into one chain per '
          'run. Paste a run\'s action-witness.jsonl, or a run result with the '
          'chain inside it, and every link is recomputed here.',
          style: TextStyle(fontSize: 12.5, height: 1.45, color: t.inkMuted),
        ),
        const SizedBox(height: FwLayout.s3),
        _input(t),
        const SizedBox(height: FwLayout.s3),
        Row(children: [
          FilledButton.tonal(onPressed: _check, child: const Text('Recheck')),
          const SizedBox(width: FwLayout.s2),
          OutlinedButton(onPressed: _clear, child: const Text('Clear')),
        ]),
        const SizedBox(height: FwLayout.s3),
        if (_unreadable)
          const HonestNull(
              'Nothing in that text reads as witness records. That is a '
              'parse failure and not a verdict about anyone\'s bytes.')
        else if (_result == null)
          const HonestNull(
              'No chain has been checked yet. Nothing on this panel is a '
              'claim about a run until one is.')
        else
          _verdict(t, _result!),
      ]),
    );
  }

  Widget _input(FwTokens t) {
    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
      borderSide: BorderSide(color: t.line),
    );
    return TextField(
      controller: _ctrl,
      minLines: 3,
      maxLines: 8,
      style: fwMono(t, size: 11.5, color: t.inkSoft),
      decoration: InputDecoration(
        hintText: 'Paste action-witness.jsonl, or a run result JSON …',
        hintStyle: fwMono(t, size: 11.5, color: t.inkFaint),
        border: border,
        enabledBorder: border,
      ),
    );
  }

  Widget _verdict(FwTokens t, ByteWitnessChainResult r) {
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
        if (r.failureClass != null)
          Text(r.failureClass!, style: fwMono(t, size: 11.5, color: t.inkMuted)),
      ]),
      const SizedBox(height: FwLayout.s2),
      Text('${r.checked} records checked'
          '${r.brokenAt == null ? '' : ', broke at record ${r.brokenAt}'}',
          style: fwMono(t, size: 11.5, color: t.inkSoft)),
      const SizedBox(height: FwLayout.s2),
      Text(r.detail, style: fwMono(t, size: 10.5, color: t.inkFaint)),
      if (r.head != null) ...[
        const SizedBox(height: FwLayout.s2),
        HashText('head', r.head!),
      ],
      const SizedBox(height: FwLayout.s3),
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
