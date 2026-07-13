// workflow_cards.dart — the run card, step rows, and past-run rows the
// Workflows view renders. Split out so the view stays a composer.

import 'package:flutter/material.dart';

import '../models/workflow_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class WorkflowRunCard extends StatelessWidget {
  final WorkflowRun run;
  const WorkflowRunCard({super.key, required this.run});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              VerdictPill(run.status, status: run.verdict),
              const SizedBox(width: FwLayout.s3),
              Expanded(
                child: Text('${run.workflow} over ${run.endpoint}',
                    style: fwMono(t, size: 12, color: t.inkMuted)),
              ),
            ],
          ),
          const SizedBox(height: FwLayout.s3),
          for (final s in run.steps) WorkflowStepRow(step: s),
          if (run.chainHash.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            HashText('chain', run.chainHash, keep: 32),
          ],
        ],
      ),
    );
  }
}

class WorkflowStepRow extends StatelessWidget {
  final WorkflowStep step;
  const WorkflowStepRow({super.key, required this.step});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SizedBox(
                  width: 90,
                  child: Text(step.name,
                      style: fwMono(t, size: 12, weight: FontWeight.w600))),
              VerdictPill(step.status, status: step.verdict),
              if (step.integrityClean == false) ...[
                const SizedBox(width: FwLayout.s2),
                const VerdictPill('integrity flagged', status: 'drift'),
              ],
            ],
          ),
          if (step.excerpt.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(step.excerpt,
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                  style:
                      TextStyle(fontSize: 12, color: t.inkSoft, height: 1.4)),
            ),
          if (step.note.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(step.note,
                  style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
            ),
        ],
      ),
    );
  }
}

class PastRunRow extends StatelessWidget {
  final Map<String, dynamic> run;
  const PastRunRow({super.key, required this.run});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final status = '${run['status'] ?? '?'}';
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
      decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          VerdictPill(status,
              status: switch (status) {
                'VERIFIED' || 'COMPLETED' => 'verified',
                'UNVERIFIED' => 'unverifiable',
                _ => 'drift',
              }),
          const SizedBox(width: FwLayout.s3),
          Expanded(
            child: Text('${run['workflow'] ?? ''} · ${run['goal_excerpt'] ?? ''}',
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 12, color: t.inkSoft)),
          ),
          Text('${run['endpoint'] ?? ''}',
              style: fwMono(t, size: 11, color: t.inkFaint)),
        ],
      ),
    );
  }
}
