import 'package:flutter/material.dart';

import '../models/inspect_evidence_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'inspect_scorer_unit_analysis_view.dart';

class InspectEvidenceResultView extends StatelessWidget {
  final InspectImportResult result;
  const InspectEvidenceResultView({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    if (result.errorCode != null) {
      return HonestNull('${result.errorCode}: ${result.errorMessage}');
    }
    final report = result.report;
    final stored = result.stored;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
        VerdictPill('reported ${report?.reportedStatus ?? 'unknown'}',
            status: _reportedStatus(report)),
        if (report != null)
          VerdictPill('assessment ${report.assessment}',
              status: _assessmentStatus(report)),
        if (report != null)
          VerdictPill(
            report.coverageComplete == true
                ? 'coverage complete'
                : 'coverage incomplete',
            status: report.coverageComplete == true && !report.invalidated
                ? 'verified'
                : 'drift',
          ),
        if (report != null)
          VerdictPill(report.countsLabel, status: 'unverifiable'),
        if (report != null)
          VerdictPill(report.scoreHistory.label, status: 'unverifiable'),
        if (report?.invalidated == true)
          const VerdictPill('invalidated true', status: 'drift'),
        const VerdictPill('semantic UNVERIFIABLE', status: 'unverifiable'),
        VerdictPill(
          stored?.present == true ? 'stored receipt' : 'not stored',
          status: stored?.present == true ? 'verified' : 'unverifiable',
        ),
      ]),
      if (stored?.present == true) ...[
        const SizedBox(height: FwLayout.s2),
        Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
          if (stored!.eid.isNotEmpty) HashText('eid', stored.eid, keep: 24),
          if (stored.sha256.isNotEmpty) HashText('stored', stored.sha256),
          if (stored.chainHash.isNotEmpty) HashText('chain', stored.chainHash),
        ]),
      ],
      if (report?.measurementUnit != null) ...[
        const SizedBox(height: FwLayout.s3),
        InspectScorerUnitAnalysisView(
          verification: report!.measurementUnit!,
        ),
      ],
      const SizedBox(height: FwLayout.s3),
      if (report == null || report.rows.isEmpty)
        const HonestNull('No source pointers were reported by this import.')
      else
        ...report.rows.map((row) => _rowTile(t, row)),
    ]);
  }

  Widget _rowTile(FwTokens t, InspectEvidenceRow row) => Material(
        type: MaterialType.transparency,
        child: ExpansionTile(
          tilePadding: EdgeInsets.zero,
          childrenPadding: const EdgeInsets.only(bottom: FwLayout.s3),
          title: Text(row.label.isEmpty ? 'reported source value' : row.label,
              style: fwMono(t, size: 11.5, color: t.ink)),
          subtitle: Text(
            [
              if (row.scorerName.isNotEmpty) row.scorerName,
              'reported ${row.reportedStatus}',
              'semantic UNVERIFIABLE',
              if (row.scoreHistoryLabel.isNotEmpty) row.scoreHistoryLabel,
              row.preview,
            ].join(' · '),
            style: TextStyle(fontSize: 12, color: t.inkMuted),
          ),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: SelectableText(
                row.sourceValueText.isEmpty
                    ? 'No source_value field was reported.'
                    : row.sourceValueText,
                style: fwMono(t, size: 11, color: t.inkSoft),
              ),
            ),
            if (row.scoreValueText.isNotEmpty)
              Align(
                alignment: Alignment.centerLeft,
                child: Text('score value: ${row.scoreValueText}',
                    style: fwMono(t, size: 11, color: t.inkMuted)),
              ),
            for (final error in row.errors)
              Align(
                alignment: Alignment.centerLeft,
                child: Text(error, style: fwMono(t, size: 11, color: t.drift)),
              ),
          ],
        ),
      );

  String _reportedStatus(InspectEvidenceReport? report) {
    if (report?.invalidated == true) return 'drift';
    return _status(report?.reportedStatus);
  }

  String _assessmentStatus(InspectEvidenceReport report) {
    if (report.invalidated || report.assessment == 'error') return 'drift';
    return report.assessment == 'reported' ? 'verified' : 'unverifiable';
  }

  String _status(String? value) => switch (value) {
        'success' => 'verified',
        'failed' || 'error' => 'drift',
        _ => 'unverifiable',
      };
}
