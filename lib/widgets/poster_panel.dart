// poster_panel.dart — the poster composer in the app: the seeded aperture
// plate typeset in the face the forge minted from the same seed, receipt
// carried on the artwork, refusals named instead of swallowed.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';

class PosterPanel extends StatefulWidget {
  final GatewayClient client;

  /// The last minted face's params: when present the plate genuinely wears
  /// it (the engine re-mints the family for the poster's type).
  final Map<String, dynamic>? faceParams;
  const PosterPanel({super.key, required this.client, this.faceParams});

  @override
  State<PosterPanel> createState() => _PosterPanelState();
}

class _PosterPanelState extends State<PosterPanel> {
  final _title = TextEditingController(text: 'order out\nof disorder');
  final _subtitle = TextEditingController();
  final _seed = TextEditingController(text: '58');
  String _format = 'poster';
  String _ground = 'dark';
  Map<String, dynamic>? _receipt;
  Uint8List? _png;
  List<String> _refusals = [];
  bool _busy = false;
  String? _savedTo, _error;

  @override
  void dispose() {
    _title.dispose();
    _subtitle.dispose();
    _seed.dispose();
    super.dispose();
  }

  Future<void> _compose() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _savedTo = null;
      _refusals = [];
    });
    try {
      final r = await widget.client.studioPoster(
        _title.text,
        subtitle: _subtitle.text,
        format: _format,
        seed: int.tryParse(_seed.text.trim()) ?? 58,
        ground: _ground,
        faceParams: widget.faceParams,
      );
      if (!mounted) return;
      setState(() {
        if (r['refused'] == true || r['error'] != null) {
          _refusals = (r['refusals'] is List)
              ? List<String>.from(r['refusals'])
              : ['${r['error'] ?? 'refused'}'];
          _png = null;
          _receipt = null;
        } else {
          _png = base64Decode('${r['png_b64']}');
          _receipt = r['receipt'] as Map<String, dynamic>?;
        }
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final png = _png;
    final rc = _receipt;
    if (png == null || rc == null) return;
    try {
      final home = Platform.environment['USERPROFILE'] ??
          Platform.environment['HOME'] ??
          '.';
      final dir = Directory('$home${Platform.pathSeparator}Downloads');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      final f = File('${dir.path}${Platform.pathSeparator}'
          'zentropy-poster-${rc['seed']}-${rc['format']}.png');
      f.writeAsBytesSync(png);
      setState(() => _savedTo = f.path);
    } catch (e) {
      setState(() => _error = 'save failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
              'The plate, the face, and your words compose deterministically: '
              'the receipt rides on the artwork, and re-running the same '
              'inputs re-derives the same bytes.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(
              flex: 2,
              child: Column(children: [
                TextField(
                  controller: _title,
                  maxLines: 2,
                  style: const TextStyle(fontSize: 13),
                  decoration:
                      const InputDecoration(hintText: 'title (lowercase face)'),
                ),
                const SizedBox(height: FwLayout.s2),
                TextField(
                  controller: _subtitle,
                  maxLines: 2,
                  style: const TextStyle(fontSize: 12.5),
                  decoration:
                      const InputDecoration(hintText: 'subtitle (optional)'),
                ),
              ]),
            ),
            const SizedBox(width: FwLayout.s3),
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              DropdownButton<String>(
                value: _format,
                isDense: true,
                style: fwMono(t, size: 11.5).copyWith(color: t.ink),
                items: [
                  for (final f in const [
                    'poster',
                    'banner',
                    'og',
                    'slide',
                    'square'
                  ])
                    DropdownMenuItem(value: f, child: Text(f)),
                ],
                onChanged: (v) => setState(() => _format = v ?? 'poster'),
              ),
              DropdownButton<String>(
                value: _ground,
                isDense: true,
                style: fwMono(t, size: 11.5).copyWith(color: t.ink),
                items: const [
                  DropdownMenuItem(value: 'dark', child: Text('dark')),
                  DropdownMenuItem(value: 'ceramic', child: Text('ceramic')),
                ],
                onChanged: (v) => setState(() => _ground = v ?? 'dark'),
              ),
              SizedBox(
                width: 90,
                child: TextField(
                  controller: _seed,
                  style: fwMono(t, size: 12),
                  decoration: const InputDecoration(hintText: 'seed'),
                ),
              ),
            ]),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _busy ? null : _compose,
              child: Text(_busy ? 'Composing…' : 'Compose'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull('Compose failed: $_error'),
          ],
          for (final r in _refusals) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull(r),
          ],
          if (_png != null) ...[
            const SizedBox(height: FwLayout.s3),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 420),
              child: Image.memory(
                _png!,
                fit: BoxFit.contain,
                filterQuality: FilterQuality.medium,
              ),
            ),
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              Expanded(
                child: HashText('poster', '${_receipt?['png_sha256'] ?? ''}',
                    keep: 16),
              ),
              Expanded(
                child: HashText('face mint',
                    '${_receipt?['face_mint_id'] ?? ''}', keep: 16),
              ),
              OutlinedButton(
                onPressed: _save,
                child: const Text('Save PNG'),
              ),
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
