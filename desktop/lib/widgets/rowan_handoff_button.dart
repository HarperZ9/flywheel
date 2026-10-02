import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../client/gateway_handoff.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

/// Copies a finished run's handoff brief so another agent can continue it.
///
/// The brief is rendered by the engine from the run's private trace. It says
/// which work was verified and which was only claimed, and it is not
/// re-checked at export time; the note under the button says so.
final class RowanHandoffButton extends StatefulWidget {
  const RowanHandoffButton(
      {super.key, required this.baseUrl, required this.operationRef, this.api});

  final String baseUrl, operationRef;

  /// Injected in tests; otherwise one client is made for this button.
  final HandoffApi? api;

  @override
  State<RowanHandoffButton> createState() => _RowanHandoffButtonState();
}

final class _RowanHandoffButtonState extends State<RowanHandoffButton> {
  late final HandoffApi _api = widget.api ?? HandoffApi(baseUrl: widget.baseUrl);
  bool _busy = false;
  String? _note, _error;

  Future<void> _copy() async {
    setState(() {
      _busy = true;
      _note = _error = null;
    });
    try {
      final brief = await _api.read(widget.operationRef);
      await Clipboard.setData(ClipboardData(text: brief.markdown));
      _note = 'Handoff brief copied: ${brief.recordCount} trace records, head '
          '${brief.traceHeadSha256.substring(0, 12)}. Not re-checked at export.';
    } on Object catch (error) {
      _error = 'Handoff brief unavailable: $error';
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TextButton.icon(
          key: const Key('rowan-copy-handoff'),
          onPressed: _busy ? null : _copy,
          icon: const Icon(Icons.ios_share_outlined, size: 14),
          label: Text(_busy ? 'Reading handoff brief' : 'Copy handoff brief'),
        ),
        // Live regions: a screen reader hears that the brief is on the
        // clipboard, or why it is not, without moving focus.
        if (_note != null)
          Semantics(
            key: const Key('rowan-handoff-note'),
            liveRegion: true,
            child: Text(_note!, style: fwMono(t, size: 10.5, color: t.inkFaint)),
          ),
        if (_error != null)
          Semantics(
            key: const Key('rowan-handoff-error'),
            liveRegion: true,
            child: HonestNull(_error!),
          ),
      ],
    );
  }
}
