import 'package:flutter/material.dart';

import '../ide/diff.dart';
import '../ide/diff_view.dart';
import '../models/writing_models.dart';
import 'fw.dart';

class WritingPanels extends StatelessWidget {
  final WritingStatus? status;
  final WritingProjectView? project;
  final WritingProposal? pending;
  final WritingProposalPreview? preview;
  final String? message;
  final bool busy;
  final TextEditingController candidate;
  final TextEditingController exportRef;
  final VoidCallback onRefresh;
  final ValueChanged<String> onOpen;
  final VoidCallback onDiagnose;
  final VoidCallback onPrepareCandidate;
  final VoidCallback onAccept;
  final VoidCallback onHold;
  final VoidCallback onExport;
  final VoidCallback onApproveCommit;

  const WritingPanels({
    super.key,
    required this.status,
    required this.project,
    required this.pending,
    required this.preview,
    required this.message,
    required this.busy,
    required this.candidate,
    required this.exportRef,
    required this.onRefresh,
    required this.onOpen,
    required this.onDiagnose,
    required this.onPrepareCandidate,
    required this.onAccept,
    required this.onHold,
    required this.onExport,
    required this.onApproveCommit,
  });

  @override
  Widget build(BuildContext context) => ViewScroll(
        storageKey: 'writing-view',
        children: [
          SectionHeader('Writing',
              kicker: 'source grounded author workflow',
              trailing: OutlinedButton(
                  onPressed: busy ? null : onRefresh,
                  child: const Text('Refresh'))),
          if (busy) ...[
            const SizedBox(height: FwLayout.s3),
            const LinearProgressIndicator(minHeight: 2),
          ],
          if (message != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull(message!),
          ],
          const SizedBox(height: FwLayout.s4),
          _projectList(),
          if (project != null) ...[
            const SizedBox(height: FwLayout.s5),
            _sourcePacket(context, project!),
            const SizedBox(height: FwLayout.s4),
            _manuscript(project!),
            const SizedBox(height: FwLayout.s4),
            _actions(),
            if (pending != null) ...[
              const SizedBox(height: FwLayout.s4),
              _proposalPanel(context),
            ],
          ],
        ],
      );

  Widget _projectList() {
    final projects = status?.projects ?? const <WritingProjectSummary>[];
    if (status == null) {
      return const HonestNull('Loading Writing projects from the gateway.');
    }
    if (projects.isEmpty) {
      return const HonestNull('No Writing projects are available yet.');
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('projects'),
      const SizedBox(height: FwLayout.s2),
      for (final item in projects) ...[
        HairlineCard(
          child: Row(children: [
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: FwLayout.s1),
                    HashText('journey', item.journeyRef),
                  ]),
            ),
            OutlinedButton(
                onPressed: busy ? null : () => onOpen(item.journeyRef),
                child: const Text('Open')),
          ]),
        ),
        const SizedBox(height: FwLayout.s2),
      ],
    ]);
  }

  Widget _sourcePacket(BuildContext context, WritingProjectView project) {
    final sources = _sourceRows(project.sourcePacket);
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('source packet', hot: true),
        const SizedBox(height: FwLayout.s2),
        HashText('project', project.projectRef),
        const SizedBox(height: FwLayout.s1),
        HashText('head', project.eventHeadSha256),
        const SizedBox(height: FwLayout.s3),
        if (sources.isEmpty)
          const HonestNull('Source packet has no listed sources.')
        else
          for (final source in sources)
            Text(_sourceLabel(source),
                style: Theme.of(context).textTheme.bodySmall),
      ]),
    );
  }

  Widget _manuscript(WritingProjectView project) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('manuscript'),
          const SizedBox(height: FwLayout.s2),
          if (project.sections.isEmpty)
            const HonestNull('No manuscript sections are recorded yet.'),
          for (final section in project.sections) ...[
            HairlineCard(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(section.heading,
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                    if ((section.currentBody ?? '').isEmpty) ...[
                      const SizedBox(height: FwLayout.s2),
                      const HonestNull('Section has no current revision.'),
                    ] else ...[
                      const SizedBox(height: FwLayout.s2),
                      SelectableText(section.currentBody!),
                    ],
                  ]),
            ),
            const SizedBox(height: FwLayout.s2),
          ],
        ],
      );

  Widget _actions() => HairlineCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Kicker('actions'),
          const SizedBox(height: FwLayout.s3),
          TextField(
            key: const Key('writing-candidate-body'),
            controller: candidate,
            maxLines: 3,
            minLines: 1,
            decoration: const InputDecoration(
              hintText: 'Candidate text supplied by the author or agent…',
            ),
          ),
          const SizedBox(height: FwLayout.s3),
          Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
            OutlinedButton(
                onPressed: busy ? null : onDiagnose,
                child: const Text('Diagnose current')),
            FilledButton(
                onPressed: busy ? null : onPrepareCandidate,
                child: const Text('Prepare candidate')),
            OutlinedButton(
                onPressed: busy ? null : onAccept,
                child: const Text('Accept latest candidate')),
            OutlinedButton(
                onPressed: busy ? null : onHold,
                child: const Text('Hold latest candidate')),
          ]),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            Expanded(
              child: TextField(
                key: const Key('writing-export-ref'),
                controller: exportRef,
                decoration:
                    const InputDecoration(hintText: 'Opaque export ref…'),
              ),
            ),
            const SizedBox(width: FwLayout.s2),
            OutlinedButton(
                onPressed: busy ? null : onExport,
                child: const Text('Prepare export')),
          ]),
        ]),
      );

  Widget _proposalPanel(BuildContext context) {
    final current = pending!;
    final shown = preview;
    final hasDiff = shown != null && shown.diffAfter.isNotEmpty;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('proposal receipt'),
        const SizedBox(height: FwLayout.s2),
        SelectableText(current.proposalRef),
        if (current.artifactKind.isNotEmpty)
          Text('${current.artifactKind} · ${current.artifactId}',
              style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: FwLayout.s3),
        FilledButton(
            onPressed: busy ? null : onApproveCommit,
            child: const Text('Approve + commit proposal')),
        if (hasDiff) ...[
          const SizedBox(height: FwLayout.s3),
          if (shown.afterSha256.isNotEmpty)
            HashText('candidate', shown.afterSha256),
          const SizedBox(height: FwLayout.s2),
          SizedBox(
            height: 260,
            child: DiffViewPanel(diffs: [
              diffFiles('writing-candidate.txt', shown.diffBefore,
                  shown.diffAfter),
            ]),
          ),
        ],
        const SizedBox(height: FwLayout.s2),
        const HonestNull(
            'This view shows recorded state and exact diffs. Semantic quality '
            'and source truth remain unmeasured unless a backend check records '
            'them.'),
      ]),
    );
  }
}

List<Map<String, dynamic>> _sourceRows(Map<String, dynamic> packet) {
  final raw = packet['sources'];
  if (raw is! List) return const [];
  return [
    for (final item in raw) if (item is Map) Map<String, dynamic>.from(item)
  ];
}

String _sourceLabel(Map<String, dynamic> row) {
  final title = row['title'];
  final sourceId = row['source_id'];
  if (title is String && title.isNotEmpty) return title;
  return sourceId is String && sourceId.isNotEmpty ? sourceId : 'source';
}
