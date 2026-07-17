// brand_kit_panel.dart — one seed and a name become a whole identity:
// mark, banner, poster, specimen, two font weights, portable tokens,
// every artifact hash bound into one kit id. Save writes the kit as a
// folder a client could be handed, provenance intact.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class BrandKitPanel extends StatefulWidget {
  final GatewayClient client;
  const BrandKitPanel({super.key, required this.client});

  @override
  State<BrandKitPanel> createState() => _BrandKitPanelState();
}

class _BrandKitPanelState extends State<BrandKitPanel> {
  final _name = TextEditingController(text: 'zentropy labs');
  final _tagline = TextEditingController(text: 'order out of disorder');
  final _seed = TextEditingController(text: '58');
  Map<String, dynamic>? _kit;
  bool _busy = false;
  String? _savedTo, _error;

  @override
  void dispose() {
    _name.dispose();
    _tagline.dispose();
    _seed.dispose();
    super.dispose();
  }

  Future<void> _mint() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
    });
    try {
      final r = await widget.client.brandKit(
        _name.text.trim(),
        tagline: _tagline.text.trim(),
        seed: int.tryParse(_seed.text.trim()) ?? 58,
      );
      if (!mounted) return;
      setState(() {
        if (r['refused'] == true || r['error'] != null) {
          _error = (r['refusals'] is List && (r['refusals'] as List).isNotEmpty)
              ? '${(r['refusals'] as List).first}'
              : '${r['error'] ?? 'refused'}';
          _kit = null;
        } else {
          _kit = r;
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final kit = _kit;
    if (kit == null) return;
    try {
      final rc = kit['receipt'] as Map<String, dynamic>;
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final slug = '${rc['brand']}'
          .replaceAll(RegExp(r'[^a-z0-9]+'), '-');
      final dir = Directory('$home${Platform.pathSeparator}Downloads'
          '${Platform.pathSeparator}kit-$slug-${rc['seed']}');
      dir.createSync(recursive: true);
      void put(String file, List<int> bytes) =>
          File('${dir.path}${Platform.pathSeparator}$file')
              .writeAsBytesSync(bytes);
      put('mark.png', base64Decode('${kit['mark_png_b64']}'));
      put('banner.png', base64Decode('${kit['banner_png_b64']}'));
      put('poster.png', base64Decode('${kit['poster_png_b64']}'));
      put('specimen.png', base64Decode('${kit['specimen_png_b64']}'));
      for (final f in (kit['fonts'] as List)) {
        put('$slug-${'${f['style']}'.toLowerCase()}.ttf',
            base64Decode('${f['ttf_b64']}'));
      }
      put('tokens.json',
          utf8.encode(const JsonEncoder.withIndent('  ')
              .convert(kit['tokens'])));
      put('receipt.json',
          utf8.encode(const JsonEncoder.withIndent('  ').convert(rc)));
      setState(() => _savedTo = dir.path);
    } catch (e) {
      setState(() => _error = 'save failed: $e');
    }
  }

  Uint8List _b(String key) => base64Decode('${_kit![key]}');

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final kit = _kit;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
              'Mark, banner, poster, specimen, two font weights, and design '
              'tokens, all from one seed and one name. The kit id binds '
              'every artifact hash, so the identity re-derives end to end.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _name,
                style: const TextStyle(fontSize: 13),
                decoration: const InputDecoration(hintText: 'brand name'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            Expanded(
              flex: 2,
              child: TextField(
                controller: _tagline,
                style: const TextStyle(fontSize: 12.5),
                decoration:
                    const InputDecoration(hintText: 'tagline (optional)'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            SizedBox(
              width: 80,
              child: TextField(
                controller: _seed,
                style: fwMono(t, size: 12),
                decoration: const InputDecoration(hintText: 'seed'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _mint,
              child: Text(_busy ? 'Minting…' : 'Mint kit'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(_error!),
          ],
          if (kit != null) ...[
            const SizedBox(height: FwLayout.s3),
            SizedBox(
              height: 210,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final key in const [
                    'mark_png_b64',
                    'banner_png_b64',
                    'poster_png_b64',
                    'specimen_png_b64'
                  ]) ...[
                    Expanded(
                      child: Image.memory(_b(key), fit: BoxFit.contain),
                    ),
                    const SizedBox(width: FwLayout.s2),
                  ],
                ],
              ),
            ),
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              VerdictPill(
                  'kit ${(kit['receipt'] as Map)['kit_id'] ?? ''}',
                  status: 'verified'),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: HashText('family',
                    '${(kit['receipt'] as Map)['family_id'] ?? ''}', keep: 16),
              ),
              OutlinedButton(onPressed: _save, child: const Text('Save kit')),
            ]),
            if (_savedTo != null) ...[
              const SizedBox(height: FwLayout.s2),
              Row(children: [
                const VerdictPill('saved', status: 'verified'),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                    child: Text(_savedTo!,
                        style: fwMono(t, size: 11).copyWith(color: t.inkMuted),
                        overflow: TextOverflow.ellipsis)),
              ]),
            ],
          ],
        ],
      ),
    );
  }
}
