import 'package:flutter/material.dart';

import '../models/inspect_evidence_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class InspectScorerUnitAnalysisView extends StatelessWidget {
  final InspectMeasurementUnitVerification verification;
  const InspectScorerUnitAnalysisView({
    super.key,
    required this.verification,
  });

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('measurement unit review'),
      const SizedBox(height: FwLayout.s2),
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        VerdictPill(
          'mapping consistency ${_displayStatus(verification.mappingConsistency)}',
          status: _pillStatus(verification.mappingConsistency),
        ),
        VerdictPill(
          'score unit ${_relationshipLabel(verification.scoreUnitRelationship)}',
          status: 'unverifiable',
        ),
        VerdictPill(
          'definition score coverage '
          '${_displayStatus(verification.definitionScoreCoverage)}',
          status: _pillStatus(verification.definitionScoreCoverage),
        ),
      ]),
      for (final contract in verification.contracts) ...[
        const SizedBox(height: FwLayout.s3),
        _ContractCard(contract: contract),
      ],
      for (final ref in verification.sourceRefs) _SourceRefLine(ref: ref),
      if (verification.doesNotProve.isNotEmpty) ...[
        const SizedBox(height: FwLayout.s2),
        HonestNull(verification.doesNotProve.join(' ')),
      ],
    ]);
  }
}

class _ContractCard extends StatelessWidget {
  final InspectScorerUnitContract contract;
  const _ContractCard({required this.contract});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      recessed: true,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(contract.scorer, style: fwMono(t, size: 12, color: t.ink)),
        const SizedBox(height: FwLayout.s2),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          VerdictPill(
              'score unit ${_relationshipLabel(contract.scoreUnitRelationship)}',
              status: 'unverifiable'),
          VerdictPill(
              'definition score coverage '
              '${_displayStatus(contract.definitionScoreCoverage)}',
              status: _pillStatus(contract.definitionScoreCoverage)),
        ]),
        const SizedBox(height: FwLayout.s3),
        AdaptiveTiles(children: [
          StatTile(
            label: 'actual scored rows',
            value: '${contract.actualScoreCardinality} '
                '${_unitLabel(contract.actualScoreUnit)}',
            status: 'unverifiable',
          ),
          StatTile(
            label: 'mapped definitions',
            value: '${contract.mappedDefinitions} '
                '${_unitLabel(contract.declaredIntendedUnit)}',
            status: 'unverifiable',
          ),
        ]),
        const SizedBox(height: FwLayout.s2),
        Text(
          'source rows ${contract.coveredSourceRows}/${contract.sourceRows} · '
          'excluded ${contract.excludedSourceRows} · '
          'declared intended ${contract.declaredIntendedCardinality}',
          style: TextStyle(fontSize: 12, color: t.inkMuted),
        ),
        for (final reason in contract.reasonCodes)
          Text(reason, style: fwMono(t, size: 11, color: t.drift)),
        for (final ref in contract.sourceRefs) _SourceRefLine(ref: ref),
        for (final ref in contract.spanRefs) _SpanRefLine(ref: ref),
      ]),
    );
  }
}

class _SourceRefLine extends StatelessWidget {
  final InspectScorerUnitSourceRef ref;
  const _SourceRefLine({required this.ref});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Padding(
      padding: const EdgeInsets.only(top: FwLayout.s2),
      child: Text('${ref.pointer} = ${ref.valueText}',
          style: fwMono(t, size: 11, color: t.inkMuted)),
    );
  }
}

class _SpanRefLine extends StatefulWidget {
  final InspectScorerUnitSpanRef ref;
  const _SpanRefLine({required this.ref});

  @override
  State<_SpanRefLine> createState() => _SpanRefLineState();
}

class _SpanRefLineState extends State<_SpanRefLine> {
  bool _showPrivate = false;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final ref = widget.ref;
    return Padding(
      padding: const EdgeInsets.only(top: FwLayout.s2),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          '${ref.unitId} · ${ref.containerPointer} · '
          'code point span ${ref.start}..${ref.end}',
          style: fwMono(t, size: 11, color: t.inkMuted),
        ),
        Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
          HashText('container', ref.containerHash, keep: 16),
          HashText('span value', ref.sourceHash, keep: 16),
        ]),
        TextButton(
          onPressed: () => setState(() => _showPrivate = !_showPrivate),
          child: Text(_showPrivate
              ? 'Hide private source context'
              : 'Show private source context'),
        ),
        if (_showPrivate) ...[
          const Kicker('private source context'),
          SelectableText(
            'Decoded embedded-string span ${ref.start}..${ref.end}:\n'
            '${ref.sourceValue}',
            style: fwMono(t, size: 11, color: t.inkSoft),
          ),
        ],
      ]),
    );
  }
}

String _pillStatus(String value) => switch (value) {
      'MATCH' => 'verified',
      'DRIFT' => 'drift',
      _ => 'unverifiable',
    };

String _displayStatus(String value) => value.toLowerCase().replaceAll('_', ' ');

String _relationshipLabel(String value) =>
    value.replaceAll('_', ' ').replaceAll('-', ' ');

String _unitLabel(String value) => switch (value) {
      'inspect_sample' => 'inspect samples',
      'python_test_function_definition' => 'python test function definitions',
      _ => value.replaceAll('_', ' '),
    };
