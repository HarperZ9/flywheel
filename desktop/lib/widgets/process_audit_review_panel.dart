import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/process_audit_review.dart';
import '../services/inspect_file_picker.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'process_audit_review_result_view.dart';

class ProcessAuditReviewPanel extends StatefulWidget {
  final GatewayClient client;
  final InspectFilePicker picker;
  const ProcessAuditReviewPanel({
    super.key,
    required this.client,
    this.picker = const FileSelectorInspectPicker(
      label: 'Process audit JSON',
      maxBytes: maxProcessAuditPacketBytes,
    ),
  });

  @override
  State<ProcessAuditReviewPanel> createState() =>
      _ProcessAuditReviewPanelState();
}

class _ProcessAuditReviewPanelState extends State<ProcessAuditReviewPanel> {
  ProcessAuditPacketUpload? _upload;
  ProcessAuditReviewResult? _result;
  String? _error;
  bool _busy = false;

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
          _upload = ProcessAuditPacketUpload.fromPickedBytes(
            picked.bytes,
            filename: picked.filename,
          );
          _result = null;
        });
      }
    } on ProcessAuditReviewException catch (error) {
      if (mounted) _fail(error.code, error.message);
    } catch (error) {
      if (mounted) _fail('INVALID_REQUEST', '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _review() async {
    final upload = _upload;
    if (_busy || upload == null) return;
    setState(() {
      _busy = true;
      _error = null;
      _result = null;
    });
    try {
      final result = await widget.client.reviewProcessAuditPacket(upload);
      if (mounted) setState(() => _result = result);
    } on ProcessAuditReviewException catch (error) {
      if (mounted) _fail(error.code, error.message);
    } catch (error) {
      if (mounted) _fail('GATEWAY_ERROR', '$error');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _fail(String code, String message) =>
      setState(() => _error = '$code: $message');

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final upload = _upload;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Kicker('review incident-sim process audit'),
        const SizedBox(height: FwLayout.s1),
        Text(
          'Select a saved process-audit packet, or an outer command report '
          'that contains audit_packet. The review sends only the inner packet '
          'bytes to the local gateway and does not save Journey state.',
          style: TextStyle(fontSize: 12.5, color: t.inkMuted),
        ),
        const SizedBox(height: FwLayout.s3),
        Wrap(spacing: FwLayout.s2, runSpacing: FwLayout.s2, children: [
          OutlinedButton(
            onPressed: _busy ? null : _pick,
            child: const Text('Select process-audit JSON'),
          ),
          FilledButton(
            onPressed: _busy || upload == null ? null : _review,
            child: Text(_busy ? 'Reviewing...' : 'Review packet'),
          ),
        ]),
        const SizedBox(height: FwLayout.s3),
        if (upload == null)
          const HonestNull('No process-audit packet has been selected.')
        else
          _uploadSummary(t, upload),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s3),
          HonestNull(_error!),
        ],
        if (_result != null) ...[
          const SizedBox(height: FwLayout.s3),
          ProcessAuditReviewResultView(result: _result!),
        ],
      ]),
    );
  }

  Widget _uploadSummary(FwTokens t, ProcessAuditPacketUpload upload) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(spacing: FwLayout.s3, runSpacing: FwLayout.s2, children: [
            HashText('source', upload.sha256, keep: 24),
            Text('${upload.byteLength} bytes',
                style: fwMono(t, size: 11.5, color: t.inkMuted)),
            Text(upload.detectedFormat,
                style: fwMono(t, size: 11.5, color: t.inkMuted)),
            if (upload.filename != null)
              Text(upload.filename!,
                  style: fwMono(t, size: 11.5, color: t.inkMuted)),
          ]),
          const SizedBox(height: FwLayout.s2),
          Material(
            type: MaterialType.transparency,
            child: ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: const EdgeInsets.only(bottom: FwLayout.s2),
              title: const Text('Local source preview'),
              subtitle: const Text('Raw private content, shown only here.'),
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: SelectableText(
                    upload.preview,
                    style: fwMono(t, size: 11, color: t.inkSoft),
                  ),
                ),
              ],
            ),
          ),
        ],
      );
}
