import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/bulletin_media_api.dart';
import '../client/gateway_client.dart';
import '../client/gateway_grants.dart';
import '../controllers/bulletin_media_authorizer.dart';
import '../controllers/bulletin_media_gateway_authorizer.dart';
import '../controllers/gateway_operation_controller.dart';
import '../controllers/journey_controller.dart';
import '../models/bulletin_media_models.dart';
import '../services/bulletin_media_cache.dart';
import '../widgets/bulletin_media_credential_picker.dart';
import '../widgets/bulletin_media_workflow_panel.dart';

final class BulletinMediaView extends StatefulWidget {
  final GatewayClient? client;
  final JourneyController? journey;
  final BulletinMediaApi? api;
  final BulletinPreparedAuthorizer? authorizer;
  final BulletinMediaLoader? mediaLoader;
  final String? initialJourneyRef, initialEventHead;

  const BulletinMediaView({super.key, this.client, this.journey, this.api,
      this.authorizer, this.mediaLoader, this.initialJourneyRef,
      this.initialEventHead});

  @override
  State<BulletinMediaView> createState() => _BulletinMediaViewState();
}

final class _BulletinMediaViewState extends State<BulletinMediaView> {
  late final BulletinMediaApi _api;
  GatewayOperationController? _grantController;
  final _run = TextEditingController();
  final _credential = TextEditingController();
  final _destination = TextEditingController();
  final _room = TextEditingController(text: 'findings');
  final _title = TextEditingController();
  final _description = TextEditingController();
  final _source = TextEditingController(text: 'Selected from a Flywheel run.');
  final _selected = <String>{};
  final _alts = <String, TextEditingController>{};
  late final _credentials = BulletinMediaCredentialSelection(_credential);
  List<BulletinMediaRun> _runs = const [];
  List<BulletinMediaArtifact> _artifacts = const [];
  BulletinMediaPreviewResponse? _preview;
  BulletinMediaPublishResult? _result;
  String? _previewFingerprint, _message;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _api = widget.api ?? GatewayBulletinMediaApi(widget.client!);
    if (widget.client != null) {
      _grantController =
          GatewayOperationController(GatewayGrantClient(widget.client!));
    }
    _loadCredentialHandles();
  }

  @override
  void dispose() {
    for (final controller in [_run, _credential, _destination, _room, _title,
      _description, _source, ..._alts.values]) {
      controller.dispose();
    }
    _grantController?.dispose();
    super.dispose();
  }

  Future<void> _loadCredentialHandles() async {
    try {
      final rows = await _api.credentialHandles();
      if (mounted) {
        setState(() { _credentials.apply(rows); _clearPublication(); });
      }
    } on Object {
      if (mounted) {
        setState(() { _credentials.fail(); _clearPublication(); });
      }
    }
  }

  void _selectCredential(BulletinMediaCredentialHandle handle) =>
      setState(() { _credentials.select(handle); _clearPublication(); });

  void _clearPublication() { _preview = null; _result = null; }

  Future<void> _loadRuns() => _runBusy(() async {
        final rows = await _api.listRuns();
        setState(() {
          _runs = rows.where((row) => !row.invalidResponse).toList();
          _clearPublication();
          _message = _runs.isEmpty ? 'No publishable media runs were returned.' : null;
        });
      });

  void _selectRun(BulletinMediaRun run) {
    setState(() {
      _run.text = run.runId;
      _artifacts = const [];
      _selected.clear();
      _clearPublication();
      _message = run.artifactCount == 0 ? 'Selected run has no artifacts.' : null;
    });
  }

  Future<void> _loadArtifacts() => _runBusy(() async {
        final rows = await _api.listArtifacts(_run.text.trim());
        final clean = rows.where((row) => !row.invalidResponse).toList();
        setState(() {
          _artifacts = clean;
          _selected
              .removeWhere((id) => clean.every((row) => row.artifactId != id));
          _clearPublication();
          _message = clean.length == rows.length
              ? null
              : 'Invalid artifact rows were hidden.';
        });
      });

  Future<void> _previewDraft() => _runBusy(() async {
        final problem = _draftProblem();
        if (problem != null) {
          setState(() => _message = problem);
          return;
        }
        final draft = _draft();
        if (draft == null || !draft.valid) {
          setState(() => _message = 'Fill a valid run, body, and alt text before preview.');
          return;
        }
        final preview = await _api.previewDraft(draft);
        setState(() {
          _preview = preview;
          _previewFingerprint = _fingerprint(draft);
          _result = null;
          _message = preview.invalidResponse && !preview.canDispatch
              ? 'Backend preview was incomplete; exact operation is required before approval.'
              : null;
        });
      });

  Future<void> _publish() => _runBusy(() async {
        final preview = _preview;
        if (preview == null) return;
        final authorizer = widget.authorizer ?? _gatewayAuthorizer;
        final outcome = await authorizer(
          context,
          preview,
          _currentOperation,
          (body) => _api.publish(body),
        );
        setState(() {
          _message = _publishMessage(outcome);
          if (!outcome.denied && outcome.failure == null) _result = outcome.value;
        });
      });

  String? _publishMessage(
      GatewayAuthorizationOutcome<BulletinMediaPublishResult> outcome) {
    final failure = outcome.failure;
    if (failure != null) return '${failure.code}: ${failure.message}';
    if (outcome.denied) return 'Publication approval was denied.';
    return outcome.value?.complete == true ? null : 'Publication is not complete.';
  }

  Future<void> _runBusy(Future<void> Function() body) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      await body();
    } on Object catch (error) {
      setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<GatewayAuthorizationOutcome<BulletinMediaPublishResult>>
      _gatewayAuthorizer(
              BuildContext context,
              BulletinMediaPreviewResponse preview,
              GatewayOperationSupplier currentOperation,
              Future<BulletinMediaPublishResult> Function(Map<String, dynamic>)
                  dispatch) =>
          authorizeBulletinMediaWithGateway(
            context,
            preview: preview,
            controller: _grantController,
            binding: _binding(),
            currentOperation: currentOperation,
            currentBinding: _binding,
            refreshOnHeadConflict: widget.journey?.refreshActiveProjection,
            dispatch: dispatch,
          );

  GatewayJourneyBinding? _binding() {
    final ref = widget.initialJourneyRef;
    final head = widget.initialEventHead;
    if (ref != null && head != null) return GatewayJourneyBinding(ref, head);
    final active = widget.journey?.state.projection;
    return active == null || active.invalidResponse ||
            widget.journey?.state.activeJourneyRef != active.journeyRef
        ? null
        : GatewayJourneyBinding(active.journeyRef, active.eventHeadSha256);
  }

  GatewayOperation? _currentOperation() {
    final preview = _preview;
    final draft = _draft();
    if (preview == null || draft == null || !draft.valid) return null;
    return _fingerprint(draft) == _previewFingerprint ? preview.operation : null;
  }

  BulletinMediaDraft? _draft() {
    final binding = _binding();
    final destination = _destinationUri();
    if (binding == null || destination == null) return null;
    final media = [
      for (final artifact in _artifacts)
        if (_selected.contains(artifact.artifactId))
          BulletinSelectedMedia(
              artifact, _alts[artifact.artifactId]?.text.trim() ?? '')
    ];
    return BulletinMediaDraft(
      runId: _run.text.trim(),
      journeyRef: binding.journeyRef,
      eventHead: binding.eventHead,
      clientRequestId: 'bulletin-media-${_run.text.trim()}',
      credentialRef: _credential.text.trim(),
      destination: destination,
      room: _room.text.trim(),
      title: _title.text.trim(),
      description: _description.text.trim(),
      sourceAttribution: _source.text.trim(),
      limits: const [
        'Upload success does not prove license, authorship, malware safety, or hidden-data absence'
      ],
      media: media,
    );
  }

  String? _draftProblem() => _binding() == null
      ? 'Open the existing identity/settings workflow before preview.'
      : _destination.text.trim().isEmpty
          ? 'Configure a Bulletin destination before preview.'
          : _destinationUri() == null
              ? 'Configure a valid Bulletin destination before preview.'
              : _credential.text.trim().isEmpty
                  ? 'Select a BULLETIN_AGENT_JWK credential handle before preview.'
                  : null;

  Uri? _destinationUri() {
    final uri = Uri.tryParse(_destination.text.trim());
    if (uri == null || !uri.hasAuthority) return null;
    final host = uri.host.toLowerCase();
    final loopback = uri.scheme == 'http' &&
        (host == 'localhost' || host == '127.0.0.1' || host == '::1');
    return uri.scheme == 'https' || loopback ? uri : null;
  }

  String _fingerprint(BulletinMediaDraft draft) => jsonEncode(draft.toJson());

  @override
  Widget build(BuildContext context) => BulletinMediaCredentialScope(
      selection: _credentials,
      onRefresh: _loadCredentialHandles,
      onSelected: _selectCredential,
      child: BulletinMediaWorkflowPanel(
        busy: _busy, runController: _run, credentialController: _credential,
        destinationController: _destination, roomController: _room,
        titleController: _title, descriptionController: _description,
        sourceController: _source, runs: _runs, artifacts: _artifacts,
        selected: _selected, altControllers: _alts, preview: _preview,
        result: _result, message: _message, loader: _loader(),
        onLoadRuns: _loadRuns, onSelectRun: _selectRun,
        onLoadArtifacts: _loadArtifacts, onPreview: _previewDraft,
        onPublish: _publish,
        onArtifactChanged: (artifact, value) => setState(() {
          value == true
              ? _selected.add(artifact.artifactId)
              : _selected.remove(artifact.artifactId);
          _preview = null;
        }),
      ));

  BulletinMediaLoader _loader() {
    final api = _api;
    final preview = _preview;
    return widget.mediaLoader ??
        (api is GatewayBulletinMediaApi && preview != null
            ? BulletinMediaCache.gateway(
                api, preview.proposal.proposalRef, preview.review.previewSha256)
            : const UnavailableBulletinMediaLoader());
  }
}
