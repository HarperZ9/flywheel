import 'package:flutter/material.dart';

import '../models/evidence_extensions.dart';
import '../models/journey_models.dart';
import 'evidence_extensions.dart';
import 'fw.dart';
import 'journey_cards.dart';

export 'journey_lens_selector.dart';

class RescueLens extends StatelessWidget {
  const RescueLens({super.key, required this.projection});
  final JourneyProjection projection;

  @override
  Widget build(BuildContext context) {
    final actions = projection.nextActions
        .where((action) => action.kind != 'rollback')
        .toList(growable: false);
    final rollback = projection.nextActions
        .where((action) => action.kind == 'rollback')
        .toList(growable: false);
    return _LensColumn(children: [
      LensDetail(projection.detail),
      RecordSection(
        title: 'Next actions',
        emptyText: projection.nextActions.isEmpty
            ? 'No next action was supplied in this projection.'
            : 'No non-rollback next action was supplied in this projection.',
        children: [for (final action in actions) ActionRecord(action: action)],
      ),
      RecordSection(
        title: 'Rollback',
        emptyText: 'No rollback action was supplied in this projection.',
        children: [for (final action in rollback) ActionRecord(action: action)],
      ),
    ]);
  }
}

class LensDetail extends StatelessWidget {
  const LensDetail(this.detail, {super.key});
  final String detail;

  @override
  Widget build(BuildContext context) => detail.isEmpty
      ? const HonestNull('The server supplied no lens detail.')
      : HairlineCard(child: Text(detail));
}

class DiagnoseLens extends StatelessWidget {
  final JourneyProjection projection;

  /// Contextual extensions render only when the server advertises them;
  /// the lens never invents a surface for an absent capability.
  final EvidenceCapability? frontierCapability;
  final FrontierAxes? frontierAxes;
  const DiagnoseLens(
      {super.key,
      required this.projection,
      this.frontierCapability,
      this.frontierAxes});

  @override
  Widget build(BuildContext context) {
    List<Widget> verdicts(bool Function(String) accepts) => [
          for (final entry in projection.rawVerdicts.entries)
            if (accepts(entry.value)) LabeledValue(entry.key, entry.value),
        ];
    return _LensColumn(children: [
      LensDetail(projection.detail),
      if (frontierCapability != null)
        FrontierClaimExtension(
            capability: frontierCapability, axes: frontierAxes),
      RecordSection(
        title: 'Support',
        emptyText: 'No PASS verdicts were supplied in this projection.',
        children: verdicts((value) => value == 'PASS'),
      ),
      RecordSection(
        title: 'Contradictions',
        emptyText: 'No FAIL verdicts were supplied in this projection.',
        children: verdicts((value) => value == 'FAIL'),
      ),
      RecordSection(
        title: 'Unresolved',
        emptyText: 'No unresolved verdicts were supplied in this projection.',
        children: verdicts((value) => value != 'PASS' && value != 'FAIL'),
      ),
      RecordSection(
        title: 'Missing evidence',
        emptyText: 'No missing evidence was supplied in this projection.',
        children: [
          for (final item in projection.missingEvidence)
            MissingRecord(item: item),
        ],
      ),
    ]);
  }
}

class VerifyLens extends StatelessWidget {
  final JourneyProjection projection;

  /// Contextual extensions: frontier claims render in Verify too.
  final EvidenceCapability? frontierCapability;
  final FrontierAxes? frontierAxes;
  const VerifyLens(
      {super.key,
      required this.projection,
      this.frontierCapability,
      this.frontierAxes});

  @override
  Widget build(BuildContext context) {
    final conclusionLimit = projection.conclusion?['does_not_prove'];
    final limits = <Widget>[
      for (final check in projection.checks)
        if (check.doesNotProve.isNotEmpty)
          LabeledValue('Check ${check.checkId}', check.doesNotProve),
      if (conclusionLimit?.isNotEmpty ?? false)
        LabeledValue('Conclusion', conclusionLimit!),
    ];
    return _LensColumn(children: [
      LensDetail(projection.detail),
      if (frontierCapability != null)
        FrontierClaimExtension(
            capability: frontierCapability, axes: frontierAxes),
      RecordSection(
        title: 'Checks',
        emptyText: 'No checks were supplied in this projection.',
        children: [
          for (final check in projection.checks) CheckRecord(check: check),
        ],
      ),
      if (projection.checks.isEmpty)
        const HonestNull('No receipt refs were supplied in this projection.'),
      RecordSection(
        title: 'Limits',
        emptyText: 'No does_not_prove limits were supplied in this projection.',
        children: limits,
      ),
    ]);
  }
}

class _LensColumn extends StatelessWidget {
  const _LensColumn({required this.children});
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (index, child) in children.indexed) ...[
            if (index > 0) const SizedBox(height: FwLayout.s4),
            child,
          ],
        ],
      );
}

class JourneyExtensionHost extends StatelessWidget {
  const JourneyExtensionHost({super.key, required this.lens});
  final JourneyLens lens;

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
