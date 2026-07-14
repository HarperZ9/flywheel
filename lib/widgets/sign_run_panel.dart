// sign_run_panel.dart — ownership as a workflow, not a checkbox. After an
// agent run, the reviewer walks the edited files, checks off exactly what
// they reviewed, and signs. The engine computes coverage and standing; a
// partial walk yields an honestly partial attestation, chained into the
// verifiable store either way.

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/attestation_models.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class SignRunPanel extends StatefulWidget {
  final GatewayClient client;
  final Map<String, dynamic> run;
  const SignRunPanel({super.key, required this.client, required this.run});

  @override
  State<SignRunPanel> createState() => _SignRunPanelState();
}

class _SignRunPanelState extends State<SignRunPanel> {
  final _note = TextEditingController();
  final _reviewer = TextEditingController();
  final Set<String> _walked = {};
  bool _signing = false;
  Attestation? _attestation;
  String? _error;

  List<String> get _edited {
    final review = widget.run['review'];
    if (review is! Map<String, dynamic>) return const [];
    final files = review['files_edited'];
    return files is List ? files.map((e) => '$e').toList() : const [];
  }

  @override
  void dispose() {
    _note.dispose();
    _reviewer.dispose();
    super.dispose();
  }

  Future<void> _sign() async {
    if (_signing) return;
    setState(() {
      _signing = true;
      _error = null;
    });
    try {
      final doc = await widget.client.attest(
        run: widget.run,
        reviewedFiles: _walked.toList(),
        note: _note.text.trim(),
        reviewer: _reviewer.text.trim(),
      );
      if (mounted) setState(() => _attestation = Attestation.fromJson(doc));
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _signing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final edited = _edited;
    final a = _attestation;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Kicker('sign this run', hot: true),
          const SizedBox(height: FwLayout.s2),
          Text(
            'Ownership with substance: check off exactly the edited files '
            'you walked. The attestation binds your sign-off to the run\'s '
            'ledger and carries its coverage; anything short of a full walk '
            'is honestly partial.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: FwLayout.s3),
          if (edited.isEmpty)
            Text('This run edited no files; a sign-off would attest to '
                'nothing. Nothing to sign.',
                style: fwMono(t, size: 11.5, color: t.inkMuted))
          else ...[
            for (final f in edited)
              Row(children: [
                Checkbox(
                  value: _walked.contains(f),
                  visualDensity: VisualDensity.compact,
                  onChanged: a != null
                      ? null
                      : (v) => setState(() =>
                          v == true ? _walked.add(f) : _walked.remove(f)),
                ),
                Expanded(child: Text(f, style: fwMono(t, size: 12))),
              ]),
            const SizedBox(height: FwLayout.s2),
            Text('walked ${_walked.length}/${edited.length}',
                style: fwMono(t, size: 11.5, color: t.inkMuted)),
            const SizedBox(height: FwLayout.s3),
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _reviewer,
                  style: const TextStyle(fontSize: 12.5),
                  decoration: const InputDecoration(hintText: 'Reviewer…'),
                ),
              ),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                flex: 2,
                child: TextField(
                  controller: _note,
                  style: const TextStyle(fontSize: 12.5),
                  decoration:
                      const InputDecoration(hintText: 'Note (optional)…'),
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              FilledButton(
                onPressed: _signing || a != null ? null : _sign,
                child: Text(_signing ? 'Signing…' : 'Sign'),
              ),
            ]),
          ],
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('Signing failed: $_error'),
          ],
          if (a != null) ...[
            const SizedBox(height: FwLayout.s3),
            Row(children: [
              VerdictPill(a.standing, status: a.verdict),
              const SizedBox(width: FwLayout.s3),
              Text('coverage ${(a.coverage * 100).round()}%',
                  style: fwMono(t, size: 12)),
              if (a.stored.isNotEmpty) ...[
                const SizedBox(width: FwLayout.s3),
                Text('stored ${a.stored}',
                    style: fwMono(t, size: 11, color: t.inkMuted)),
              ],
            ]),
            if (a.unreviewed.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('unwalked: ${a.unreviewed.join(', ')}',
                    style: fwMono(t, size: 11, color: t.inkMuted)),
              ),
            const SizedBox(height: FwLayout.s2),
            HashText('attestation', a.sha256),
            if (a.storeChainHash.isNotEmpty)
              HashText('store chain', a.storeChainHash),
          ],
        ],
      ),
    );
  }
}
