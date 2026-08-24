// The three contextual extension widgets. Each renders only what the
// server advertises: an absent or unknown capability renders nothing at
// all, an execution-locked one states its lock in plain text, and no
// widget ever derives a verdict or a composite.
import 'package:flutter/material.dart';

import '../models/evidence_extensions.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

/// Incident Compiler: renders only inside an active Journey when the
/// capability is advertised. A proposal is a proposed graph; the widget
/// says so and offers no accept.
class IncidentExtension extends StatelessWidget {
  final EvidenceCapability? capability;
  final IncidentProposal? proposal;
  const IncidentExtension(
      {super.key, required this.capability, this.proposal});

  @override
  Widget build(BuildContext context) {
    final cap = capability;
    if (cap == null || !cap.renderable) return const SizedBox.shrink();
    final t = context.fw;
    final p = proposal;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('incident compiler', hot: true),
          const SizedBox(height: FwLayout.s2),
          if (cap.executionLocked)
            HonestNull(cap.reason)
          else if (p == null)
            Text('Compile a proposed check graph from the admitted facts.',
                style: TextStyle(fontSize: 12.5, color: t.inkMuted))
          else ...[
            Text('Proposal ${p.proposalId.substring(0, 12.clamp(0, p.proposalId.length))}… '
                '(${p.state})',
                style: fwMono(t, size: 12, color: t.ink)),
            const SizedBox(height: FwLayout.s2),
            HonestNull(p.doesNotProve),
          ],
        ],
      ),
    );
  }
}

/// Frontier Claims: renders inside Diagnose and Verify only, with the
/// four axes as separate labeled groups and raw unrecognized values kept
/// visible. No composite, no score, no verdict inference.
class FrontierClaimExtension extends StatelessWidget {
  final EvidenceCapability? capability;
  final FrontierAxes? axes;
  const FrontierClaimExtension(
      {super.key, required this.capability, this.axes});

  @override
  Widget build(BuildContext context) {
    final cap = capability;
    if (cap == null || !cap.renderable) return const SizedBox.shrink();
    final t = context.fw;
    final rows = axes?.axes ?? const <FrontierAxis>[];
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('frontier claims · four independent axes', hot: true),
          const SizedBox(height: FwLayout.s2),
          if (rows.isEmpty)
            Text('No axes projected yet.',
                style: TextStyle(fontSize: 12.5, color: t.inkMuted))
          else
            for (final axis in rows) ...[
              Text(axis.axis,
                  style: fwMono(t, size: 11, color: t.inkSoft)),
              const SizedBox(height: 2),
              for (final entry in axis.fields.entries)
                Padding(
                  padding: const EdgeInsets.only(left: 12, bottom: 2),
                  child: Text('${entry.key}: ${entry.value ?? 'null'}',
                      style: fwMono(t, size: 11, color: t.inkMuted)),
                ),
              for (final raw in axis.rawUnrecognized)
                Padding(
                  padding: const EdgeInsets.only(left: 12, bottom: 2),
                  child: Text('unrecognized, preserved: $raw',
                      style: fwMono(t, size: 10.5, color: t.unverifiable)),
                ),
              const SizedBox(height: FwLayout.s2),
            ],
        ],
      ),
    );
  }
}

/// Domain Packs: shows the pack's admitted state; an execution-locked
/// pack says so in text and never gains an execute control.
class DomainPackExtension extends StatelessWidget {
  final EvidenceCapability? capability;
  final DomainPackProjection? projection;
  const DomainPackExtension(
      {super.key, required this.capability, this.projection});

  @override
  Widget build(BuildContext context) {
    final cap = capability;
    if (cap == null || !cap.renderable) return const SizedBox.shrink();
    final t = context.fw;
    final p = projection;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('domain pack', hot: true),
          const SizedBox(height: FwLayout.s2),
          if (cap.executionLocked)
            HonestNull('Execution locked: ${cap.reason}.')
          else if (p == null)
            Text('No pack projected.',
                style: TextStyle(fontSize: 12.5, color: t.inkMuted))
          else ...[
            VerdictPill(p.state == 'available' ? 'available' : 'data only',
                status: p.state == 'available' ? 'verified' : 'unverifiable'),
            const SizedBox(height: FwLayout.s2),
            HonestNull(p.doesNotProve),
          ],
        ],
      ),
    );
  }
}
