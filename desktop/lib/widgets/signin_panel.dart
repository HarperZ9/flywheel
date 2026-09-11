// signin_panel.dart — subscription sign-in, one row per provider.
import 'dart:async';

import 'package:flutter/material.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

part 'signin_panel_row.dart';

class SigninPanel extends StatefulWidget {
  final Map<String, dynamic> doc;
  final Future<Map<String, dynamic>> Function(String provider) onLogin;
  final Future<Map<String, dynamic>> Function(String provider, String token)
      onToken;
  final Future<Map<String, dynamic>> Function(String provider) onLogout;
  final Future<Map<String, dynamic>> Function(String provider)? onCancel;
  final Future<Map<String, dynamic>> Function(String provider)?
      onCheckExecution;
  final VoidCallback onChanged;
  final Future<bool> Function(String url)? onOpenUrl;
  const SigninPanel(
      {super.key,
      required this.doc,
      required this.onLogin,
      required this.onToken,
      required this.onLogout,
      required this.onChanged,
      this.onOpenUrl,
      this.onCancel,
      this.onCheckExecution});
  @override
  State<SigninPanel> createState() => _SigninPanelState();
}

class _SigninPanelState extends State<SigninPanel> {
  static const _routeCheckTimeout = Duration(seconds: 20);

  final _paste = TextEditingController();
  String? _guided; // provider whose steps are open
  List<String> _steps = const [];
  String? _deviceProvider, _deviceUrl, _deviceCode;
  String? _routeCheckProvider;
  Timer? _routeCheckTimer;
  String? _note;
  bool _busy = false;
  @override
  void dispose() {
    _routeCheckTimer?.cancel();
    _paste.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(SigninPanel old) {
    super.didUpdateWidget(old);
    if (old.doc != widget.doc) _reconcileDeviceCodeWithDoc();
  }

  Future<void> _start(String provider) async {
    final row = _provider(provider);
    final kind = '${row?['kind'] ?? ''}';
    setState(() {
      _busy = true;
      _note = null;
    });
    try {
      final r = await widget.onLogin(provider);
      if (!mounted) return;
      final url = r['authorize_url'];
      if (r['mode'] == 'guided' && r['ok'] == true) {
        setState(() {
          _guided = provider;
          _steps = ((r['steps'] ?? []) as List).map((s) => '$s').toList();
        });
      } else if (r['mode'] == 'device-code' && r['ok'] == true) {
        final verification = '${r['verification_url'] ?? ''}';
        if (!_trustedSignInUrl(kind, verification)) {
          setState(() => _note = 'blocked an untrusted sign-in URL');
        } else {
          if (widget.onOpenUrl != null) {
            await widget.onOpenUrl!(verification);
            if (!mounted) return;
          }
          setState(() {
            _deviceProvider = provider;
            _deviceUrl = verification;
            _deviceCode = '${r['user_code'] ?? ''}';
            _note = 'enter the device code to finish ChatGPT sign-in';
          });
        }
      } else if (url is String && url.isNotEmpty && widget.onOpenUrl != null) {
        if (!_trustedSignInUrl(kind, url)) {
          setState(() => _note = 'blocked an untrusted sign-in URL');
          return;
        }
        final opened = await widget.onOpenUrl!(url);
        if (!mounted) return;
        if (!opened && widget.onCancel != null) {
          try {
            await widget.onCancel!(provider);
          } catch (_) {}
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
        _note = ok
            ? 'credential stored ${r['stored']}; authentication unverified'
            : '${r['error']}';
      });
      if (ok) _paste.clear();
      widget.onChanged();
    } catch (_) {
      if (mounted) {
        setState(
            () => _note = 'could not store the token; check engine status');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _out(String provider, {bool cancel = false}) async {
    setState(() {
      _busy = true;
      _note = null;
    });
    try {
      final r = await (cancel
          ? widget.onCancel!(provider)
          : widget.onLogout(provider));
      if (!mounted) return;
      final ok = r['ok'] == true;
      setState(() {
        if (ok) _clearDeviceCode();
        _note = ok
            ? (cancel
                ? 'sign-in cancelled locally'
                : 'local credential removed for $provider')
            : '${r['error'] ?? (cancel ? 'could not cancel sign-in' : 'could not sign out')}';
      });
      if (ok || !cancel) widget.onChanged();
    } catch (_) {
      if (mounted) {
        setState(() =>
            _note = cancel ? 'could not cancel sign-in' : 'could not sign out');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _closeGuided() {
    setState(() {
      _guided = null;
      _steps = const [];
      _paste.clear();
    });
  }

  void _clearDeviceCode() {
    _deviceProvider = null;
    _deviceUrl = null;
    _deviceCode = null;
  }

  void _reconcileDeviceCodeWithDoc() {
    final provider = _deviceProvider;
    if (provider == null) return;
    final p = _provider(provider);
    if (p == null) {
      _clearDeviceCode();
      _note = null;
      return;
    }
    final kind = '${p['kind'] ?? ''}';
    final accountKey =
        kind == 'official-app-server' ? 'official_app_server' : 'official_cli';
    final account = (p[accountKey] is Map)
        ? Map<String, dynamic>.from(p[accountKey] as Map)
        : <String, dynamic>{};
    final authenticated =
        account['authenticated'] == true || p['present'] == true;
    final last = '${p['last'] ?? ''}';
    final state = '${account['account_state'] ?? account['state'] ?? ''}';
    const terminalMarkers = {
      'authenticated',
      'cancelled',
      'done',
      'expired',
      'failed',
      'logged_out',
      'logout',
      'signed_out',
      'timed_out',
      'timeout',
    };
    if (authenticated ||
        terminalMarkers.contains(last) ||
        terminalMarkers.contains(state)) {
      _clearDeviceCode();
      _note = null;
    }
  }

  Future<void> _checkExecution(String provider) async {
    if (widget.onCheckExecution == null || _routeCheckProvider != null) {
      return;
    }
    setState(() {
      _busy = true;
      _routeCheckProvider = provider;
      _note = null;
    });
    try {
      final read = widget.onCheckExecution!(provider);
      _routeCheckTimer?.cancel();
      _routeCheckTimer = Timer(_routeCheckTimeout, () {
        if (!mounted || _routeCheckProvider != provider) return;
        setState(() {
          _busy = false;
          _note = 'route check timed out; waiting for the gateway before retry';
        });
      });
      final r = await read;
      if (!mounted) return;
      _routeCheckTimer?.cancel();
      setState(() {
        _routeCheckProvider = null;
        _busy = false;
        _note = _routeCheckNote(provider, r);
      });
    } catch (_) {
      _routeCheckTimer?.cancel();
      if (mounted) {
        setState(() {
          _routeCheckProvider = null;
          _busy = false;
          _note = 'could not run the route check';
        });
      }
    }
  }

  String _routeCheckNote(String provider, Map<String, dynamic> doc) {
    if (doc['ok'] == false) {
      return '${doc['error'] ?? 'route check did not complete'}';
    }
    final row = _providerInDoc(doc, provider);
    if (row == null) {
      return 'bounded Codex CLI route check refreshed; provider row was not returned';
    }
    final account = (row['official_app_server'] is Map)
        ? Map<String, dynamic>.from(row['official_app_server'] as Map)
        : <String, dynamic>{};
    final routeReady =
        account['route_ready'] == true || row['route_ready'] == true;
    if (routeReady) return 'bounded Codex CLI route check passed';
    final reason = _firstText([
      account['route_ready_reason'],
      row['route_ready_reason'],
      account['run_ready_reason'],
      row['run_ready_reason'],
      _probeReason(account['readiness_probe']),
      _probeReason(row['readiness_probe']),
      row['last_error'],
      account['error'],
    ]);
    return reason.isEmpty
        ? 'bounded Codex CLI route check did not report route readiness'
        : 'bounded Codex CLI route check did not pass: $reason';
  }

  Map<String, dynamic>? _providerInDoc(
      Map<String, dynamic> doc, String provider) {
    final providers = doc['providers'];
    if (providers is List) {
      for (final p in providers.whereType<Map>()) {
        final row = Map<String, dynamic>.from(p);
        if ('${row['provider']}' == provider) return row;
      }
    }
    if ('${doc['provider'] ?? ''}' == provider) return doc;
    return null;
  }

  String _probeReason(Object? probe) {
    if (probe is String) return probe;
    if (probe is Map) {
      return _firstText([
        probe['reason'],
        probe['error'],
        probe['status'],
        probe['exit_code'],
      ]);
    }
    return '';
  }

  String _firstText(Iterable<Object?> values) {
    for (final value in values) {
      final text = '${value ?? ''}'.trim();
      if (text.isNotEmpty) return text;
    }
    return '';
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
}
