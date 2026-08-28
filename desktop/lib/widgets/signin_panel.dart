// signin_panel.dart — subscription sign-in, one row per provider.
//
// A monthly subscription can carry usage instead of a raw key. Each provider
// states its own terms rather than being flattened into one button: a
// documented browser flow, a provider's own tool, or an app registration the
// operator owns. The token itself is never displayed, and a paste leaves this
// widget the moment it is handed to the engine.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class SigninPanel extends StatefulWidget {
  final Map<String, dynamic> doc;
  final Future<Map<String, dynamic>> Function(String provider) onLogin;
  final Future<Map<String, dynamic>> Function(String provider, String token)
      onToken;
  final Future<Map<String, dynamic>> Function(String provider) onLogout;
  final VoidCallback onChanged;

  const SigninPanel({
    super.key,
    required this.doc,
    required this.onLogin,
    required this.onToken,
    required this.onLogout,
    required this.onChanged,
  });

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

  // Every handler follows the same shape: set _busy, do the work in a try, and
  // reset _busy in a finally so the button always re-enables. _busy is one
  // field shared by every row, so a stuck call would otherwise disable the
  // whole panel. A throw (a non-200 from the engine, or a timed-out call to a
  // remote/paired engine) surfaces its reason in _note instead of vanishing.
  Future<void> _start(String provider) async {
    setState(() {
      _busy = true;
      _note = null;
    });
    try {
      final r = await widget.onLogin(provider);
      if (!mounted) return;
      setState(() {
        if (r['mode'] == 'guided' && r['ok'] == true) {
          _guided = provider;
          _steps = ((r['steps'] ?? []) as List).map((s) => '$s').toList();
        } else {
          _note = r['ok'] == true
              ? '${r['note'] ?? 'sign-in started'}'
              : '${r['error'] ?? 'sign-in did not start'}';
        }
      });
      widget.onChanged();
    } catch (e) {
      if (mounted) {
        setState(() => _note = 'sign-in could not reach the engine: $e');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submit(String provider) async {
    final value = _paste.text;
    if (value.isEmpty) return;
    setState(() {
      _busy = true;
      _note = null;
    });
    try {
      final r = await widget.onToken(provider, value);
      if (!mounted) return;
      final ok = r['ok'] == true;
      setState(() {
        _guided = null;
        _steps = const [];
        _note = ok ? 'signed in; stored ${r['stored']}' : '${r['error']}';
      });
      // The token leaves this widget only once it is stored, so a failed
      // attempt keeps the paste and the user can retry without re-entering it.
      if (ok) _paste.clear();
      widget.onChanged();
    } catch (e) {
      if (mounted) {
        setState(() => _note = 'could not store the token: $e');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _out(String provider) async {
    setState(() {
      _busy = true;
      _note = null;
    });
    try {
      final r = await widget.onLogout(provider);
      if (!mounted) return;
      setState(() {
        _note = r['ok'] == true ? 'signed out of $provider' : '${r['error']}';
      });
      widget.onChanged();
    } catch (e) {
      if (mounted) {
        setState(() => _note = 'could not sign out: $e');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final providers = ((widget.doc['providers'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    final storeOk = widget.doc['credential_store'] == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${widget.doc['note'] ?? ''}',
            style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        if (!storeOk) ...[
          const SizedBox(height: FwLayout.s2),
          const HonestNull(
              'No OS credential store on this platform, so a sign-in could '
              'not keep its token. Use the provider tool and export the '
              'variable instead.'),
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
    final present = p['present'] == true;
    final pending = p['pending'] == true;
    final open = _guided == provider;
    return Padding(
      padding: const EdgeInsets.only(bottom: FwLayout.s3),
      child: HairlineCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                VerdictDot(present ? 'verified' : 'unverifiable', size: 7),
                const SizedBox(width: FwLayout.s2),
                Text(provider,
                    style: const TextStyle(
                        fontSize: 13, fontWeight: FontWeight.w600)),
                const SizedBox(width: FwLayout.s2),
                Text('${p['kind_label'] ?? p['kind']}',
                    style: fwMono(t, size: 10, color: t.inkFaint)),
                const Spacer(),
                if (pending)
                  Text('waiting for the browser',
                      style: fwMono(t, size: 10, color: t.inkMuted))
                else if (present)
                  TextButton(
                    onPressed: _busy ? null : () => _out(provider),
                    child: const Text('Sign out'),
                  )
                else
                  FilledButton(
                    onPressed: _busy ? null : () => _start(provider),
                    child: const Text('Sign in'),
                  ),
              ],
            ),
            const SizedBox(height: FwLayout.s2),
            // The terms, always visible: what this provider actually permits
            // is not something the app decides on the user's behalf.
            Text('${p['sanction'] ?? ''}',
                style: TextStyle(fontSize: 11, color: t.inkFaint)),
            if (present)
              Padding(
                padding: const EdgeInsets.only(top: FwLayout.s1),
                child: Text('token in ${p['source']}:${p['keychain_name']}',
                    style: fwMono(t, size: 10, color: t.inkMuted)),
              ),
            if ('${p['last_error'] ?? ''}'.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: FwLayout.s1),
                child: Text('${p['last_error']}',
                    style: fwMono(t, size: 10, color: t.drift)),
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
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _paste,
                      obscureText: true, // the value is never shown back
                      autocorrect: false,
                      enableSuggestions: false,
                      style: fwMono(t, size: 11),
                      decoration: const InputDecoration(
                        isDense: true,
                        hintText: 'Paste the token the tool printed',
                      ),
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
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
