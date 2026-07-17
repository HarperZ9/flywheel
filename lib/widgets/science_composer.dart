// science_composer.dart — the Science workbench's input card: a question,
// stated claims with their falsification criteria, and — the part that
// makes a verdict reachable — an optional measurement per claim. Crucible's
// contract is blunt: an unmeasured claim is UNVERIFIABLE forever; only a
// measurement {deviation, tolerance, method, evidence} can flip it to a
// witnessed MATCH or DRIFT.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class ScienceClaim {
  final text = TextEditingController();
  final falsification = TextEditingController();
  final deviation = TextEditingController();
  final tolerance = TextEditingController();
  final method = TextEditingController();
  final evidence = TextEditingController();
  bool measured = false;

  Map<String, String>? claimJson(int i) {
    if (text.text.trim().isEmpty) return null;
    return {
      'id': 'c${i + 1}',
      'text': text.text.trim(),
      'falsification': falsification.text.trim(),
    };
  }

  /// The measurement rides only when it carries content; a blank expander
  /// must not fabricate a zero-deviation "measurement".
  Map<String, dynamic>? measurementJson(int i) {
    if (!measured) return null;
    final dev = double.tryParse(deviation.text.trim());
    if (dev == null || method.text.trim().isEmpty) return null;
    return {
      'claim': 'c${i + 1}',
      'deviation': dev,
      'tolerance': double.tryParse(tolerance.text.trim()) ?? 0.0,
      'method': method.text.trim(),
      'evidence': evidence.text.trim(),
    };
  }

  void dispose() {
    for (final c in [text, falsification, deviation, tolerance, method, evidence]) {
      c.dispose();
    }
  }
}

class ScienceComposer extends StatelessWidget {
  final TextEditingController question;
  final List<ScienceClaim> claims;
  final bool running;
  final VoidCallback onAddClaim;
  final ValueChanged<int> onRemoveClaim;
  final ValueChanged<int> onToggleMeasured;
  final VoidCallback onRun;
  const ScienceComposer(
      {super.key,
      required this.question,
      required this.claims,
      required this.running,
      required this.onAddClaim,
      required this.onRemoveClaim,
      required this.onToggleMeasured,
      required this.onRun});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: question,
            maxLines: 2,
            minLines: 1,
            style: const TextStyle(fontSize: 13.5),
            decoration: const InputDecoration(hintText: 'The research question…'),
          ),
          const SizedBox(height: FwLayout.s3),
          for (final (i, c) in claims.indexed) ...[
            Row(children: [
              Text('c${i + 1}', style: fwMono(t, size: 11, color: t.inkFaint)),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: TextField(
                  controller: c.text,
                  style: const TextStyle(fontSize: 12.5),
                  decoration: const InputDecoration(hintText: 'Claim…'),
                ),
              ),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: TextField(
                  controller: c.falsification,
                  style: const TextStyle(fontSize: 12.5),
                  decoration:
                      const InputDecoration(hintText: 'What would falsify it…'),
                ),
              ),
              TextButton(
                onPressed: () => onToggleMeasured(i),
                child: Text(c.measured ? 'unmeasure' : 'measure',
                    style: fwMono(t,
                        size: 10.5,
                        color: c.measured ? t.ink : t.inkFaint)),
              ),
              IconButton(
                icon: const Icon(Icons.close, size: 14),
                onPressed: () => onRemoveClaim(i),
              ),
            ]),
            if (c.measured) ...[
              const SizedBox(height: FwLayout.s1),
              Row(children: [
                const SizedBox(width: 24),
                SizedBox(
                  width: 90,
                  child: TextField(
                    controller: c.deviation,
                    style: fwMono(t, size: 11.5),
                    decoration: const InputDecoration(hintText: 'deviation'),
                  ),
                ),
                const SizedBox(width: FwLayout.s2),
                SizedBox(
                  width: 90,
                  child: TextField(
                    controller: c.tolerance,
                    style: fwMono(t, size: 11.5),
                    decoration: const InputDecoration(hintText: 'tolerance'),
                  ),
                ),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                  child: TextField(
                    controller: c.method,
                    style: const TextStyle(fontSize: 12),
                    decoration: const InputDecoration(
                        hintText: 'method — how it was measured'),
                  ),
                ),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                  child: TextField(
                    controller: c.evidence,
                    style: const TextStyle(fontSize: 12),
                    decoration: const InputDecoration(
                        hintText: 'evidence — file, link, or receipt'),
                  ),
                ),
              ]),
            ],
            const SizedBox(height: FwLayout.s2),
          ],
          Row(children: [
            OutlinedButton(
              onPressed: onAddClaim,
              child: const Text('Add claim'),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: running ? null : onRun,
              child: Text(running ? 'Running…' : 'Run'),
            ),
            const SizedBox(width: FwLayout.s3),
            Flexible(
              child: Text(
                  'a measured claim can reach MATCH or DRIFT; an unmeasured '
                  'one stays UNVERIFIABLE',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: fwMono(t, size: 10, color: t.inkFaint)),
            ),
          ]),
        ],
      ),
    );
  }
}
