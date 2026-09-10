// signin_panel.dart — subscription sign-in, one row per provider.
import 'package:flutter/material.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class SigninPanel extends StatefulWidget {
  final Map<String, dynamic> doc;
  final Future<Map<String, dynamic>> Function(String provider) onLogin;
  final Future<Map<String, dynamic>> Function(String provider, String token) onToken;
  final Future<Map<String, dynamic>> Function(String provider) onLogout;
  final Future<Map<String, dynamic>> Function(String provider)? onCancel;
  final VoidCallback onChanged;
  final Future<bool> Function(String url)? onOpenUrl;
  const SigninPanel({super.key, required this.doc, required this.onLogin,
      required this.onToken, required this.onLogout, required this.onChanged,
      this.onOpenUrl, this.onCancel});
  @override
  State<SigninPanel> createState() => _SigninPanelState();
}

class _SigninPanelState extends State<SigninPanel> {
  final _paste = TextEditingController();
  String? _guided; // provider whose steps are open
  List<String> _steps = const [];
  String? _note;
  bool _busy = false;
  @override
  void dispose() {
    _paste.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(SigninPanel old) {
    super.didUpdateWidget(old);
    if (!_busy && old.doc != widget.doc) _note = null;
  }

  Future<void> _start(String provider) async {
    setState(() { _busy = true; _note = null; });
    try {
      final r = await widget.onLogin(provider);
      if (!mounted) return;
      final url = r['authorize_url'];
      if (r['mode'] == 'guided' && r['ok'] == true) {
        setState(() {
          _guided = provider;
          _steps = ((r['steps'] ?? []) as List).map((s) => '$s').toList();
        });
      } else if (url is String && url.isNotEmpty && widget.onOpenUrl != null) {
        final opened = await widget.onOpenUrl!(url);
        if (!mounted) return;
        if (!opened && widget.onCancel != null) {
          try { await widget.onCancel!(provider); } catch (_) {}
          if (!mounted) return;
        }
        setState(() => _note = opened
            ? 'opening the sign-in page; approve it, then return here'
            : 'could not open the sign-in page on this device');
      } else {
        setState(() => _note = r['ok'] == true
            ? '${r['note'] ?? 'sign-in started'}'
            : '${r['error'] ?? 'sign-in did not start'}');
      }
      widget.onChanged();
    } catch (_) {
      if (mounted) setState(() => _note = 'sign-in could not reach the engine');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submit(String provider) async {
    final value = _paste.text;
    if (value.isEmpty) return;
    setState(() { _busy = true; _note = null; });
    try {
      final r = await widget.onToken(provider, value);
      if (!mounted) return;
      final ok = r['ok'] == true;
      setState(() {
        _guided = null; _steps = const [];
        _note = ok ? 'credential stored ${r['stored']}; authentication unverified' : '${r['error']}';
      });
      if (ok) _paste.clear();
      widget.onChanged();
    } catch (_) {
      if (mounted) setState(() => _note = 'could not store the token; check engine status');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _out(String provider, {bool cancel = false}) async {
    setState(() { _busy = true; _note = null; });
    try {
      final r = await (cancel ? widget.onCancel!(provider) : widget.onLogout(provider));
      if (!mounted) return;
      setState(() {
        _note = r['ok'] == true
            ? (cancel ? 'sign-in cancelled locally' : 'local credential removed for $provider')
            : '${r['error']}';
      });
      widget.onChanged();
    } catch (_) {
      if (mounted) setState(() => _note = cancel ? 'could not cancel sign-in' : 'could not sign out');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final providers = ((widget.doc['providers'] ?? []) as List).whereType<Map<String, dynamic>>().toList();
    final storeOk = widget.doc['credential_store'] == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${widget.doc['note'] ?? ''}', style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        if (!storeOk) ...[
          const SizedBox(height: FwLayout.s2),
          const HonestNull(
              'No OS credential store: token-storing providers cannot keep '
              'a token on this platform. '
              'Claude Code account sign-in stays inside Claude Code.'),
        ],
        if (_note != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text(_note!, style: fwMono(t, size: 10.5, color: t.inkMuted)),
        ],
        const SizedBox(height: FwLayout.s3),
        if (providers.isEmpty)
          const HonestNull(
              'The engine declared no sign-in providers. A provider appears '
              'here once the engine ships its profile.')
        else
          for (final p in providers) _row(t, p),
      ],
    );
  }

  Widget _row(FwTokens t, Map<String, dynamic> p) {
    final provider = '${p['provider']}';
    final kind = '${p['kind']}';
    final official = kind == 'official-cli';
    final account = (p['official_cli'] is Map) ? Map<String, dynamic>.from(p['official_cli'] as Map) : <String, dynamic>{};
    final accountState = '${account['state'] ?? p['source'] ?? 'unknown'}';
    final accountAuth = account['authenticated'] == true || (official && p['present'] == true);
    final present = official ? accountAuth : p['present'] == true;
    final pending = p['pending'] == true;
    final open = !official && _guided == provider;
    final waitText = official ? 'waiting for Claude Code' : 'waiting for the browser';
    final buttonText = official ? 'Open sign-in' : 'Sign in';
    final accountText = accountAuth
        ? 'Claude Code account authenticated'
        : switch (accountState) {
            'not_authenticated' => 'Claude Code account not signed in',
            'cli_absent' => 'Claude Code CLI absent',
            'wrapper_unsupported' => 'Claude Code wrapper unsupported',
            _ => 'Claude Code account unknown',
          };
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                VerdictDot(official && accountAuth ? 'verified' : 'unverifiable', size: 7),
                const SizedBox(width: FwLayout.s2),
                Text(provider,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600)),
                const SizedBox(width: FwLayout.s2),
                Text('${p['kind_label'] ?? kind}',
                    style: fwMono(t, size: 10, color: t.inkFaint)),
                const Spacer(),
                if (pending) ...[
                  Text(waitText, style: fwMono(t, size: 10, color: t.inkMuted)),
                  if (widget.onCancel != null)
                    TextButton(
                      onPressed: _busy ? null : () => _out(provider, cancel: true),
                      child: const Text('Cancel'),
                    ),
                ] else if (present && !official)
                  TextButton(
                    onPressed: _busy ? null : () => _out(provider),
                    child: const Text('Sign out'),
                  )
                else if (present && official)
                  TextButton(
                    onPressed: _busy ? null : widget.onChanged,
                    child: const Text('Refresh'),
                  )
                else
                  FilledButton(
                    onPressed: _busy ? null : () => _start(provider),
                    child: Text(buttonText),
                  ),
              ],
            ),
            const SizedBox(height: FwLayout.s2),
            if (official)
              Text(accountText)
            else ...[
              if (!pending && p['last'] == 'done' && present)
                const Text('credential stored'),
              if (present) const Text('credential present; authentication unverified'),
            ],
            if (p['last'] == 'cancelled') const Text('sign-in cancelled locally'),
            Text('${p['sanction'] ?? ''}', style: TextStyle(fontSize: 11, color: t.inkFaint)),
            if (present && !official)
              Padding(
                padding: const EdgeInsets.only(top: FwLayout.s1),
                child: Text('token in ${p['source']}:${p['keychain_name']}', style: fwMono(t, size: 10, color: t.inkMuted)),
              ),
            if ('${p['last_error'] ?? ''}'.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: FwLayout.s1),
                child: Text('${p['last_error']}', style: fwMono(t, size: 10, color: t.drift)),
              ),
            if (open) ...[
              const SizedBox(height: FwLayout.s3),
              for (var i = 0; i < _steps.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text('${i + 1}. ${_steps[i]}',
                      style: TextStyle(fontSize: 11.5, color: t.ink)),
                ),
              const SizedBox(height: FwLayout.s2),
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: _paste,
                    obscureText: true,
                    autocorrect: false,
                    enableSuggestions: false,
                    style: fwMono(t, size: 11),
                    decoration: const InputDecoration(
                        isDense: true,
                        hintText: 'Paste the token the tool printed'),
                    onSubmitted: (_) => _submit(provider),
                  ),
                ),
                const SizedBox(width: FwLayout.s2),
                FilledButton(
                  onPressed: _busy ? null : () => _submit(provider),
                  child: const Text('Store'),
                ),
                TextButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                            _guided = null;
                            _steps = const [];
                            _paste.clear();
                          }),
                  child: const Text('Cancel'),
                ),
              ]),
            ],
          ],
        ),
      ),
    );
  }
}
