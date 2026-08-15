import 'package:flutter/material.dart';

import '../models/journey_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

String verdictStatus(String raw) => switch (raw) {
      'PASS' => 'verified',
      'FAIL' => 'drift',
      _ => 'unverifiable',
    };

String receiptStatus(String raw) => switch (raw) {
      'MATCH' => 'verified',
      'DRIFT' || 'TAMPERED' => 'drift',
      _ => 'unverifiable',
    };

String readableWire(String raw) => raw.replaceAll('_', ' ');

class JourneyCoreCard extends StatelessWidget {
  const JourneyCoreCard({super.key, required this.projection});
  final JourneyProjection projection;

  @override
  Widget build(BuildContext context) {
    final conclusion = projection.conclusion;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('Shared evidence'),
          const SizedBox(height: FwLayout.s3),
          HashText('Journey ref', projection.journeyRef, keep: 36),
          const SizedBox(height: FwLayout.s2),
          Semantics(
            label: 'Event head ${projection.eventHeadSha256}',
            container: true,
            excludeSemantics: true,
            child: HashText('Event head', projection.eventHeadSha256),
          ),
          const SizedBox(height: FwLayout.s3),
          LabeledValue('Stage', projection.rawStage),
          const SizedBox(height: FwLayout.s3),
          ValueCollection(
            title: 'Fact IDs',
            values: projection.factIds,
            emptyText: 'No fact IDs were supplied in this projection.',
          ),
          const SizedBox(height: FwLayout.s3),
          ValueCollection(
            title: 'Claim IDs',
            values: projection.claimIds,
            emptyText: 'No claim IDs were supplied in this projection.',
          ),
          const SizedBox(height: FwLayout.s3),
          _CoreVerdicts(projection.rawVerdicts),
          const SizedBox(height: FwLayout.s3),
          if (conclusion == null)
            const HonestNull('No conclusion was supplied in this projection.')
          else ...[
            LabeledValue(
                'Conclusion',
                conclusion['summary'] ??
                    'No conclusion summary was supplied in this projection.'),
            const SizedBox(height: FwLayout.s2),
            LabeledValue(
                'Conclusion does_not_prove',
                conclusion['does_not_prove'] ??
                    'No conclusion does_not_prove limit was supplied in this projection.'),
          ],
        ],
      ),
    );
  }
}

class _CoreVerdicts extends StatelessWidget {
  const _CoreVerdicts(this.values);
  final Map<String, String> values;

  @override
  Widget build(BuildContext context) {
    if (values.isEmpty) {
      return const HonestNull('No verdicts were supplied in this projection.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Verdicts', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: FwLayout.s2),
        for (final entry in values.entries) ...[
          Wrap(
            spacing: FwLayout.s2,
            runSpacing: FwLayout.s1,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              DataText(entry.key),
              VerdictPill(entry.value, status: verdictStatus(entry.value)),
            ],
          ),
          if (entry != values.entries.last) const SizedBox(height: FwLayout.s2),
        ],
      ],
    );
  }
}

class ValueCollection extends StatelessWidget {
  const ValueCollection({
    super.key,
    required this.title,
    required this.values,
    required this.emptyText,
  });
  final String title, emptyText;
  final List<String> values;

  @override
  Widget build(BuildContext context) {
    if (values.isEmpty) return HonestNull(emptyText);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: FwLayout.s2),
        Wrap(
          spacing: FwLayout.s3,
          runSpacing: FwLayout.s2,
          children: [for (final value in values) DataText(value)],
        ),
      ],
    );
  }
}

class LabeledValue extends StatelessWidget {
  const LabeledValue(this.label, this.value, {super.key});
  final String label, value;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: FwLayout.s2,
        runSpacing: FwLayout.s1,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          DataText(value),
        ],
      );
}

class DataText extends StatelessWidget {
  const DataText(this.value, {super.key});
  final String value;

  @override
  Widget build(BuildContext context) => SelectableText(
        value,
        style: fwMono(context.fw, size: 12),
      );
}

class RecordSection extends StatelessWidget {
  const RecordSection({
    super.key,
    required this.title,
    required this.children,
    required this.emptyText,
  });
  final String title, emptyText;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: FwLayout.s2),
          if (children.isEmpty)
            HonestNull(emptyText)
          else
            HairlineCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final (index, child) in children.indexed) ...[
                    if (index > 0) ...[
                      const SizedBox(height: FwLayout.s3),
                      const Divider(),
                      const SizedBox(height: FwLayout.s3),
                    ],
                    child,
                  ],
                ],
              ),
            ),
        ],
      );
}

class ActionRecord extends StatelessWidget {
  const ActionRecord({super.key, required this.action});
  final JourneyNextAction action;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(action.description,
              style: Theme.of(context).textTheme.bodyLarge),
          const SizedBox(height: FwLayout.s2),
          LabeledValue('Action ID', action.actionId),
          const SizedBox(height: FwLayout.s1),
          LabeledValue('Kind', action.kind),
          const SizedBox(height: FwLayout.s2),
          ValueCollection(
            title: 'Basis refs',
            values: action.basisRefs,
            emptyText: 'No basis refs were supplied for this action.',
          ),
        ],
      );
}

class MissingRecord extends StatelessWidget {
  const MissingRecord({super.key, required this.item});
  final JourneyMissingEvidence item;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LabeledValue('Kind', item.kind),
          const SizedBox(height: FwLayout.s1),
          LabeledValue('Evidence ID', item.id),
          const SizedBox(height: FwLayout.s2),
          ValueCollection(
            title: 'Receipt refs',
            values: item.receiptRefs,
            emptyText:
                'No receipt refs were supplied for this missing evidence.',
          ),
        ],
      );
}

class CheckRecord extends StatelessWidget {
  const CheckRecord({super.key, required this.check});
  final JourneyCheck check;

  @override
  Widget build(BuildContext context) {
    final rawVerdict = check.rawVerdict;
    final rawReceipt = check.rawReceiptState;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        LabeledValue('Check ID', check.checkId),
        const SizedBox(height: FwLayout.s1),
        LabeledValue('Claim ID', check.claimId),
        const SizedBox(height: FwLayout.s2),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          if (rawVerdict == null || rawVerdict.isEmpty)
            const HonestNull('No verdict was supplied for this check.')
          else
            VerdictPill(rawVerdict, status: verdictStatus(rawVerdict)),
          if (rawReceipt == null || rawReceipt.isEmpty)
            const HonestNull('No receipt state was supplied for this check.')
          else
            VerdictPill(readableWire(rawReceipt),
                status: receiptStatus(rawReceipt)),
        ]),
        const SizedBox(height: FwLayout.s2),
        if (rawReceipt != null && rawReceipt.isNotEmpty) ...[
          LabeledValue('Receipt state', readableWire(rawReceipt)),
          const SizedBox(height: FwLayout.s2),
        ],
        LabeledValue('Coverage', '${check.numerator} / ${check.denominator}'),
        const SizedBox(height: FwLayout.s2),
        ValueCollection(
          title: 'Receipt refs',
          values: check.receiptRefs,
          emptyText: 'No receipt refs were supplied for this check.',
        ),
        const SizedBox(height: FwLayout.s2),
        if (check.doesNotProve.isEmpty)
          const HonestNull(
              'No does_not_prove limit was supplied for this check.')
        else
          LabeledValue('does_not_prove', check.doesNotProve),
      ],
    );
  }
}
