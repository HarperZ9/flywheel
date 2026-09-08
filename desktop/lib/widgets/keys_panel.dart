// keys_panel.dart — provider credentials, handled the only acceptable way:
// typed once into an obscured field, stored in the OS keychain, shown
// forever after as presence and source only. No value is ever displayed,
// logged, or echoed back.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

class KeysPanel extends StatefulWidget {
  final Map<String, dynamic> doc;
  final Map<String, dynamic>? bulletinIdentity;
  final Future<Map<String, dynamic>> Function(String name, String value) onSet;
  final Future<Map<String, dynamic>> Function(String name) onDelete;
  final Future<Map<String, dynamic>> Function()? onCreateBulletinIdentity;
  final Future<Map<String, dynamic>> Function()? onRegisterBulletinIdentity;
  final VoidCallback onChanged;
  const KeysPanel(
      {super.key,
      required this.doc,
      this.bulletinIdentity,
      required this.onSet,
      required this.onDelete,
      this.onCreateBulletinIdentity,
      this.onRegisterBulletinIdentity,
      required this.onChanged});

  @override
  State<KeysPanel> createState() => _KeysPanelState();
}

class _KeysPanelState extends State<KeysPanel> {
  String? _editing;
  final _value = TextEditingController();
  String? _note;

  @override
  void dispose() {
    _value.dispose();
    super.dispose();
  }

  Future<void> _save(String name) async {
    final v = _value.text;
    if (v.isEmpty) return;
    try {
      final r = await widget.onSet(name, v);
      _value.clear(); // the secret leaves this widget immediately
      setState(() {
        _editing = null;
        _note = _resultNote(r, 'stored $name');
      });
      widget.onChanged();
    } catch (e) {
      if (mounted) setState(() => _note = 'could not store key: $e');
    }
  }

  Future<void> _nativeAction(
      Future<Map<String, dynamic>> Function()? action, String fallback) async {
    if (action == null) {
      setState(() => _note = 'native Bulletin identity setup is unavailable');
      return;
    }
    try {
      final r = await action();
      if (!mounted) return;
      final ok = r['error'] == null;
      setState(() => _note = _resultNote(r, fallback));
      if (ok) widget.onChanged();
    } catch (e) {
      if (mounted) {
        setState(() => _note = 'could not update Bulletin identity: $e');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final entries = ((widget.doc['entries'] ?? []) as List)
        .whereType<Map<String, dynamic>>()
        .toList();
    final available = widget.doc['available'] == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${widget.doc['note'] ?? ''}',
            style: TextStyle(fontSize: 11.5, color: t.inkFaint)),
        if (!available) ...[
          const SizedBox(height: FwLayout.s2),
          const HonestNull(
              'No supported OS credential store on this platform; the '
              'environment variables keep working.'),
        ],
        if (_note != null) ...[
          const SizedBox(height: FwLayout.s2),
          Text(_note!, style: fwMono(t, size: 10.5, color: t.inkMuted)),
        ],
        const SizedBox(height: FwLayout.s3),
        if (entries.isEmpty)
          // An empty roster is stated, never blank: without it a fresh
          // install shows nothing and the user has no idea keys exist.
          const HonestNull(
              'The engine declared no provider key names. Hosted providers '
              'appear here (with a Set path) once the engine ships provider '
              'definitions; local tiers need no key.')
        else
          HairlineCard(
            padding: const EdgeInsets.symmetric(
                horizontal: FwLayout.s4, vertical: FwLayout.s2),
            child: Column(
              children: [for (final e in entries) _row(t, e, available)],
            ),
          ),
      ],
    );
  }

  Widget _row(FwTokens t, Map<String, dynamic> e, bool available) {
    final name = '${e['name']}';
    final source = '${e['source']}';
    final editing = _editing == name;
    if (_isBulletinIdentity(e)) return _bulletinRow(t, name, source, available);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
      decoration:
          BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          Expanded(child: Text(name, style: fwMono(t, size: 11.5))),
          if (editing) ...[
            SizedBox(
              width: 220,
              child: TextField(
                controller: _value,
                obscureText: true,
                autofocus: true,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(
                    hintText: 'paste key, stores on enter'),
                onSubmitted: (_) => _save(name),
              ),
            ),
            const SizedBox(width: FwLayout.s2),
            OutlinedButton(
              onPressed: () => setState(() {
                _editing = null;
                _value.clear();
              }),
              child: const Text('Cancel'),
            ),
          ] else ...[
            VerdictPill(
                switch (source) {
                  'env' => 'env',
                  'keychain' => 'keychain',
                  _ => 'absent',
                },
                status: source == 'absent' ? 'absent' : 'verified'),
            const SizedBox(width: FwLayout.s2),
            if (available)
              OutlinedButton(
                onPressed: () => setState(() => _editing = name),
                child: const Text('Set'),
              ),
            if (source == 'keychain') ...[
              const SizedBox(width: FwLayout.s2),
              OutlinedButton(
                onPressed: () async {
                  final r = await widget.onDelete(name);
                  if (!mounted) return;
                  setState(() => _note =
                      r['error'] != null ? '${r['error']}' : 'removed $name');
                  widget.onChanged();
                },
                child: const Text('Remove'),
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _bulletinRow(FwTokens t, String name, String source, bool available) {
    final status = widget.bulletinIdentity ?? const {};
    final nativeSource = '${status['source'] ?? source}';
    final nativeKeychain = status['keychain_available'] is bool
        ? status['keychain_available'] == true
        : available;
    final signing = status['signing_available'] is bool
        ? status['signing_available'] == true
        : true;
    final unavailable =
        _nativeUnavailable(nativeSource, nativeKeychain, signing);
    return Container(
      padding: const EdgeInsets.symmetric(vertical: FwLayout.s2),
      decoration:
          BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
      child: Row(
        children: [
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(name, style: fwMono(t, size: 11.5)),
              Text(
                unavailable ??
                    'native identity; no pasted key or displayed value',
                style: TextStyle(fontSize: 11, color: t.inkFaint),
              ),
            ]),
          ),
          VerdictPill(
              switch (nativeSource) {
                'env' => 'env',
                'keychain' => 'keychain',
                _ => 'absent',
              },
              status: nativeSource == 'absent' ? 'absent' : 'verified'),
          const SizedBox(width: FwLayout.s2),
          if (nativeSource == 'absent')
            OutlinedButton(
              onPressed: unavailable == null
                  ? () => _nativeAction(widget.onCreateBulletinIdentity,
                      'created Bulletin identity')
                  : null,
              child: const Text('Create identity'),
            ),
          if (nativeSource == 'keychain') ...[
            OutlinedButton(
              onPressed: unavailable == null
                  ? () => _nativeAction(widget.onRegisterBulletinIdentity,
                      'registered Bulletin identity')
                  : null,
              child: const Text('Register'),
            ),
            const SizedBox(width: FwLayout.s2),
            OutlinedButton(
              onPressed: () async {
                final r = await widget.onDelete(name);
                if (!mounted) return;
                setState(() => _note = _resultNote(r, 'removed $name'));
                widget.onChanged();
              },
              child: const Text('Remove'),
            ),
          ],
        ],
      ),
    );
  }
}

bool _isBulletinIdentity(Map<String, dynamic> row) =>
    row['name'] == 'BULLETIN_AGENT_JWK' ||
    row['set_action'] == 'bulletin_identity' ||
    row['kind'] == 'native_identity' ||
    row['generic_set_allowed'] == false;

String? _nativeUnavailable(
    String source, bool keychainAvailable, bool signingAvailable) {
  if (!keychainAvailable) {
    return 'OS keychain unavailable; environment still works';
  }
  if (!signingAvailable) return 'signing support is unavailable in this build';
  if (source == 'env') {
    return 'managed by environment; unset env to manage here';
  }
  return null;
}

String _resultNote(Map<String, dynamic> r, String fallback) {
  final error = r['error'];
  if (error is Map && error['code'] is String) {
    return _fixedError('${error['code']}');
  }
  if (error != null) return '$error';
  return '${r['action'] ?? fallback}';
}

String _fixedError(String code) => switch (code) {
      'SIGNING_UNAVAILABLE' => 'signing support is unavailable in this build',
      'KEYCHAIN_UNAVAILABLE' => 'OS keychain is unavailable',
      'STORE_BUSY' => 'identity storage is busy',
      'KEYCHAIN_VALUE_EXISTS' => 'identity already exists in the OS keychain',
      'NATIVE_IDENTITY_MISSING' => 'create an identity before registering',
      'BOARD_STATUS_UNAVAILABLE' => 'Bulletin status could not be read',
      'REGISTRATION_UNAVAILABLE' =>
        'Bulletin registration could not be reached',
      'REGISTRATION_FAILED' => 'Bulletin registration failed',
      'POW_BITS_UNSUPPORTED' =>
        'Bulletin registration work factor is unsupported',
      'ENV_CREDENTIAL_PRESENT' =>
        'environment value blocks keychain management',
      _ => code,
    };
