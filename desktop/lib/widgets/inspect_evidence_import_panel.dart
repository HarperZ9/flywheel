import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../controllers/journey_controller.dart';
import '../models/gateway_grant_models.dart';
import '../models/inspect_evidence_models.dart';
import '../services/inspect_file_picker.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'inspect_import_approval_controls.dart';
import 'inspect_evidence_result_view.dart';
import 'inspect_evidence_upload_summary.dart';
import 'operation_grant_sheet.dart';

class InspectEvidenceImportPanel extends StatefulWidget {
  final GatewayClient client;
  final JourneyController? journey;
  final InspectFilePicker picker, unitContractPicker;
  const InspectEvidenceImportPanel({
    super.key,
    required this.client,
    this.journey,
    this.picker = const FileSelectorInspectPicker(),
    this.unitContractPicker = const FileSelectorInspectPicker(
      label: 'Inspect scorer unit sidecar',
      maxBytes: maxInspectUnitContractUploadBytes,
    ),
  });

  @override
  State<InspectEvidenceImportPanel> createState() =>
      _InspectEvidenceImportPanelState();
}

class _InspectEvidenceImportPanelState
    extends State<InspectEvidenceImportPanel> {
  InspectEvidenceUpload? _upload;
  GatewayOperation? _activeOperation;
  InspectImportResult? _result;
  InspectImportList? _recent;
  String? _recentError;
  String? _error;
  bool _busy = false, _loadingRecent = false;

  @override
  void initState() {
    super.initState();
    _loadRecent();
  }

  Future<void> _loadRecent() async {
    if (_loadingRecent) return;
    setState(() {
      _loadingRecent = true;
      _recentError = null;
    });
    try {
      final list = await widget.client.listInspectEvidenceImports(limit: 10);
      if (!mounted) return;
      setState(() {
        _recent = list;
        _recentError = list.errorCode == null
            ? null
            : '${list.errorCode}: ${list.errorMessage}';
      });
    } catch (error) {
      if (mounted) setState(() => _recentError = '$error');
    } finally {
      if (mounted) setState(() => _loadingRecent = false);
    }
  }

  Future<void> _pick() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final picked = await widget.picker.pick();
      if (picked != null && mounted) {
        setState(() {
          _upload = InspectEvidenceUpload.fromBytes(
            picked.bytes,
            filename: picked.filename,
          );
          _activeOperation = null;
          _result = null;
        });
      }
    } on InspectEvidenceUploadException catch (error) {
      if (mounted) _fail(error.code, error.message);
    } catch (error) {
      if (mounted) _fail('INVALID_REQUEST', '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pickUnitContract() async {
    final upload = _upload;
    if (_busy || upload == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final picked = await widget.unitContractPicker.pick();
      if (picked != null && mounted) {
        setState(() => _upload = upload.withUnitContract(
              InspectUnitContractUpload.fromBytes(
                picked.bytes,
                filename: picked.filename,
              ),
            ));
      }
    } on InspectEvidenceUploadException catch (error) {
      if (mounted) _fail(error.code, error.message);
    } catch (error) {
      if (mounted) _fail('INVALID_REQUEST', '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _requestApproval() async {
    final upload = _upload;
    if (_busy || upload == null) return;
    final operation = upload.operation();
    setState(() {
      _busy = true;
      _activeOperation = operation;
      _error = null;
      _result = null;
    });
    try {
      final outcome =
          await authorizeGatewayOperationDetailed<InspectImportResult>(
        context,
        operation,
        (body) => _dispatchUpload(upload, body),
        currentOperation: () => _activeOperation,
      );
      if (!mounted) return;
      if (outcome.denied) {
        _fail('APPROVAL_DENIED', 'Inspect upload was not approved.');
      } else if (outcome.failure != null) {
        _fail(outcome.failure!.code, outcome.failure!.message);
      } else {
        setState(() => _result = outcome.value);
        await _loadRecent();
      }
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _activeOperation = null;
        });
      }
    }
  }

  Future<void> _openRecent(InspectImportListItem item) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _result = null;
    });
    try {
      final result = await widget.client.readInspectEvidenceImport(item.eid);
      if (mounted) setState(() => _result = result);
    } catch (error) {
      if (mounted) _fail('GATEWAY_ERROR', '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<InspectImportResult> _dispatchUpload(
    InspectEvidenceUpload upload,
    Map<String, dynamic> body,
  ) async {
    final journey = body['journey_ref'];
    final head = body['expected_event_head'];
    final grant = body['grant_ref'];
    if (journey is! String || head is! String || grant is! String) {
      return const InspectImportResult.error(
        'INVALID_RESPONSE',
        'Gateway approval did not return an upload binding.',
      );
    }
    try {
      return await widget.client.uploadInspectEvidence(
        upload,
        binding: GatewayJourneyBinding(journey, head),
        grantRef: grant,
      );
    } on InspectEvidenceUploadException catch (error) {
      return InspectImportResult.error(error.code, error.message);
    }
  }

  void _fail(String code, String message) =>
      setState(() => _error = '$code: $message');

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final upload = _upload;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('import Inspect evidence'),
          const SizedBox(height: FwLayout.s1),
          Text(
            'Select local Inspect JSON bytes, approve the exact digest and '
            'length in the Journey grant sheet, then save the reported import '
            'receipt. Scores remain reported data.',
            style: TextStyle(fontSize: 12.5, color: t.inkMuted),
          ),
          const SizedBox(height: FwLayout.s3),
          InspectImportApprovalControls(
            busy: _busy,
            upload: upload,
            journey: widget.journey,
            onPick: _pick,
            onPickUnitContract: _pickUnitContract,
            onRequestApproval: _requestApproval,
          ),
          if (upload == null) ...[
            const SizedBox(height: FwLayout.s3),
            const HonestNull('No Inspect JSON has been selected.'),
          ] else ...[
            const SizedBox(height: FwLayout.s3),
            InspectEvidenceUploadSummary(upload: upload),
          ],
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull(_error!),
          ],
          if (_result != null) ...[
            const SizedBox(height: FwLayout.s3),
            InspectEvidenceResultView(result: _result!),
          ],
          const SizedBox(height: FwLayout.s3),
          _recentBlock(t),
        ],
      ),
    );
  }

  Widget _recentBlock(FwTokens t) {
    final list = _recent;
    if (_recentError != null) return HonestNull(_recentError!);
    if (_loadingRecent && list == null) {
      return Text('Reading saved Inspect imports...',
          style: fwMono(t, size: 11.5, color: t.inkMuted));
    }
    if (list == null || list.items.isEmpty) {
      return const HonestNull('No saved Inspect imports were reported.');
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Kicker('recent Inspect imports'),
      const SizedBox(height: FwLayout.s2),
      for (final item in list.items) _recentRow(t, item),
    ]);
  }

  Widget _recentRow(FwTokens t, InspectImportListItem item) => Padding(
        padding: const EdgeInsets.only(bottom: FwLayout.s2),
        child: Row(children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.eid, style: fwMono(t, size: 11.5, color: t.ink)),
                Text(
                  '${item.byteLength} bytes · reported '
                  '${item.reportedStatus} · semantic UNVERIFIABLE',
                  style: TextStyle(fontSize: 12, color: t.inkMuted),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: _busy ? null : () => _openRecent(item),
            child: const Text('Open'),
          ),
        ]),
      );
}
