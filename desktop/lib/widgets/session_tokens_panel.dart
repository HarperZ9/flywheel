// session_tokens_panel.dart — active session tokens: scoped, time-bounded
// agent credentials. Shows which sessions hold a token, how many slots it
// covers, and time remaining, with a revoke path. The token_ref value itself
// is never rendered — only used to key the revoke call.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class SessionTokensPanel extends StatefulWidget {
  final Map<String, dynamic> doc;
  final Future<Map<String, dynamic>> Function(String tokenRef) onRevoke;
  final VoidCallback onChanged;

  const SessionTokensPanel({
    super.key,
    required this.doc,
    required this.onRevoke,
    required this.onChanged,
  });

  @override
  State<SessionTokensPanel> createState() => _SessionTokensPanelState();
}

class _SessionTokensPanelState extends State<SessionTokensPanel> {
  String? _busy;
  String? _note;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final tokens = ((widget.doc['tokens'] as List?) ?? [])
        .whereType<Map<String, dynamic>>()
        .toList();
    if (tokens.isEmpty) {
      return const HonestNull('No active session tokens.');
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        HairlineCard(
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s4, vertical: FwLayout.s2),
          child: Column(
            children: [for (final tok in tokens) _row(t, tok)],
          ),
        ),
        if (_note != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text(_note!, style: fwMono(t, size: 10.5, color: t.inkMuted)),
        ],
      ],
    );
  }

  Widget _row(FwTokens t, Map<String, dynamic> tok) {
    final session = tok['session_ref'] as String? ?? 'unknown';
    final slots = tok['slots'] as int? ?? 0;
    final expiresAt = tok['expires_at'] as num? ?? 0;
    final remaining = Duration(
        seconds: (expiresAt - DateTime.now().millisecondsSinceEpoch / 1000)
            .round()
            .clamp(0, 99999));
    final ref = tok['token_ref'] as String? ?? '';
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2 + 2),
      decoration:
          BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(session,
                    style: fwMono(t, size: 12, weight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text('$slots slots · ${_fmt(remaining)} remaining',
                    style: TextStyle(fontSize: 11.5, color: t.inkMuted)),
              ],
            ),
          ),
          TextButton(
            onPressed: _busy == ref ? null : () => _revoke(ref),
            child: Text(_busy == ref ? 'Revoking…' : 'Revoke'),
          ),
        ],
      ),
    );
  }

  String _fmt(Duration d) {
    if (d.inHours > 0) return '${d.inHours}h ${d.inMinutes % 60}m';
    return '${d.inMinutes}m';
  }

  Future<void> _revoke(String ref) async {
    setState(() {
      _busy = ref;
      _note = null;
    });
    try {
      await widget.onRevoke(ref);
      if (!mounted) return;
      setState(() => _note = null);
      widget.onChanged();
    } catch (e) {
      if (mounted) setState(() => _note = 'could not revoke: $e');
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }
}
