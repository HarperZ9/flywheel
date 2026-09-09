import 'dart:async';

import 'package:flutter/material.dart';

import '../client/writing_api.dart';
import '../models/writing_models.dart';
import '../widgets/fw.dart';
import '../widgets/writing_panels.dart';

class WritingView extends StatefulWidget {
  final WritingApi api;
  final bool alive;

  const WritingView({super.key, required this.api, required this.alive});

  @override
  State<WritingView> createState() => _WritingViewState();
}

class _WritingViewState extends State<WritingView> {
  final _candidate = TextEditingController();
  final _exportRef = TextEditingController(text: 'draft');
  WritingStatus? _status;
  WritingProjectView? _project;
  WritingProposal? _pending;
  WritingProposalPreview? _preview;
  String? _message;
  String? _latestCandidateRef;
  bool _busy = false;
  int _requestSeq = 0;

  @override
  void initState() {
    super.initState();
    if (widget.alive) unawaited(_refresh());
  }

  @override
  void didUpdateWidget(covariant WritingView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!oldWidget.alive && widget.alive) unawaited(_refresh());
  }

  @override
  void dispose() {
    _candidate.dispose();
    _exportRef.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty(
        'The engine is offline. Writing projects appear when it runs.',
        command: 'flywheel up',
      );
    }
    return WritingPanels(
      status: _status,
      project: _project,
      pending: _pending,
      preview: _preview,
      message: _message,
      busy: _busy,
      candidate: _candidate,
      exportRef: _exportRef,
      onRefresh: () => unawaited(_refresh()),
      onOpen: (journeyRef) => unawaited(_open(journeyRef)),
      onDiagnose: () => unawaited(_diagnose()),
      onPrepareCandidate: () => unawaited(_prepareCandidate()),
      onAccept: () => unawaited(_decision('accept')),
      onHold: () => unawaited(_decision('reject')),
      onReview: () => unawaited(_review()),
      onExport: () => unawaited(_export()),
      onApproveCommit: () => unawaited(_approveCommit()),
    );
  }

  Future<void> _refresh() => _run(() async {
        final next = await widget.api.status();
        if (mounted) setState(() => _status = next);
      });

  Future<void> _open(String journeyRef) => _run(() async {
        final next = await widget.api.project(journeyRef);
        if (!mounted) return;
        setState(() {
          _project = next;
          _message = null;
        });
      });

  Future<void> _diagnose() => _run(() async {
        final project = _requireProject();
        final revisionRef = project.firstCurrentSection?.currentRevisionRef;
        if (revisionRef == null || revisionRef.isEmpty) {
          throw StateError('No current revision to diagnose.');
        }
        await _captureProposal(await widget.api.prepareDiagnose(
          journeyRef: project.journeyRef,
          expectedEventHead: project.eventHeadSha256,
          projectRef: project.projectRef,
          revisionRef: revisionRef,
          clientRequestId: _requestId('diagnose'),
        ));
      });

  Future<void> _prepareCandidate() => _run(() async {
        final project = _requireProject();
        final cardRef = project.firstCardRef;
        final body = _candidate.text;
        if (cardRef == null) {
          throw StateError('No diagnosis card is available.');
        }
        if (body.trim().isEmpty) throw StateError('Candidate text is empty.');
        final proposal = await widget.api.prepareCandidate(
          journeyRef: project.journeyRef,
          expectedEventHead: project.eventHeadSha256,
          projectRef: project.projectRef,
          cardRef: cardRef,
          body: body,
          clientRequestId: _requestId('candidate'),
        );
        _latestCandidateRef = proposal.artifactId;
        await _captureProposal(proposal);
      });

  Future<void> _decision(String decision) => _run(() async {
        final project = _requireProject();
        final candidateRef = _latestCandidateRef ?? project.firstCandidateRef;
        if (candidateRef == null) {
          throw StateError('No candidate is available.');
        }
        await _captureProposal(await widget.api.prepareDecision(
          journeyRef: project.journeyRef,
          expectedEventHead: project.eventHeadSha256,
          projectRef: project.projectRef,
          decision: decision,
          candidateRef: candidateRef,
          reason:
              decision == 'reject' ? 'author hold from native Writing' : null,
          clientRequestId: _requestId(decision),
        ));
      });

  Future<void> _review() => _run(() async {
        final project = _requireProject();
        await _captureProposal(await widget.api.prepareReview(
          journeyRef: project.journeyRef,
          expectedEventHead: project.eventHeadSha256,
          projectRef: project.projectRef,
          clientRequestId: _requestId('review'),
        ));
      });

  Future<void> _export() => _run(() async {
        final project = _requireProject();
        final outRef = _exportRef.text.trim();
        if (outRef.isEmpty) throw StateError('Export ref is empty.');
        await _captureProposal(await widget.api.prepareExport(
          journeyRef: project.journeyRef,
          expectedEventHead: project.eventHeadSha256,
          projectRef: project.projectRef,
          outRef: outRef,
          clientRequestId: _requestId('export'),
        ));
      });

  Future<void> _approveCommit() => _run(() async {
        final pending = _pending;
        if (pending == null) throw StateError('No proposal is pending.');
        final approved = await widget.api.approve(pending.proposalRef);
        final grantRef = approved['grant_ref'];
        if (grantRef is! String || grantRef.isEmpty) {
          throw StateError('Approved proposal did not return a grant ref.');
        }
        await widget.api.commit(pending.proposalRef, grantRef);
        final current = _project;
        if (current != null) await _open(current.journeyRef);
        if (!mounted) return;
        setState(() {
          _pending = null;
          _preview = null;
        });
      });

  Future<void> _captureProposal(WritingProposal proposal) async {
    final preview = await widget.api.proposalGet(proposal.proposalRef);
    if (!mounted) return;
    setState(() {
      _pending = proposal;
      _preview = preview;
      _message = null;
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    if (!mounted) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await action();
    } catch (error) {
      if (mounted) setState(() => _message = _cleanError(error));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  WritingProjectView _requireProject() {
    final project = _project;
    if (project == null) throw StateError('Open a Writing project first.');
    return project;
  }

  String _requestId(String action) {
    _requestSeq += 1;
    return 'native_writing_${action}_$_requestSeq';
  }
}

String _cleanError(Object error) {
  final text = error.toString();
  if (text.startsWith('Exception: ')) return text.substring(11);
  if (text.startsWith('Bad state: ')) return text.substring(11);
  return text;
}
