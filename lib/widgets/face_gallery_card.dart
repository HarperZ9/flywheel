// face_gallery_card.dart — the marketplace of minted faces. Publish the face
// on the bench into the witnessed gallery, browse every published face, and
// wear one to preview it in place. A listing carries only metadata; the .ttf
// arrives on the fetch that wears it, so browsing never ships fonts nobody
// asked for. Every face re-derives from its stored seed and params.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../theme/flywheel_theme.dart';
import 'fw.dart';
import 'typeface_panel.dart' show loadFontFamily;

class FaceGalleryCard extends StatefulWidget {
  final GatewayClient client;

  /// The face on the bench right now (last mint's params incl. 'seed'), so
  /// it can be published without re-minting; null disables Publish.
  final Map<String, dynamic>? benchFace;
  const FaceGalleryCard({super.key, required this.client, this.benchFace});

  @override
  State<FaceGalleryCard> createState() => _FaceGalleryCardState();
}

class _FaceGalleryCardState extends State<FaceGalleryCard> {
  List<Map<String, dynamic>> _faces = [];
  bool _loading = false, _publishing = false;
  String? _error, _wornFamily;
  final Set<String> _loaded = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (_loading) return;
    setState(() => _loading = true);
    try {
      final doc = await widget.client.typefaceGallery();
      if (mounted) {
        setState(() => _faces = ((doc['faces'] ?? []) as List)
            .whereType<Map<String, dynamic>>()
            .toList());
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _publish() async {
    final fp = widget.benchFace;
    if (fp == null || _publishing) return;
    setState(() {
      _publishing = true;
      _error = null;
    });
    try {
      final seed = fp['seed'] is int ? fp['seed'] as int : 58;
      final params = {...fp}..remove('seed');
      final r = await widget.client.typefacePublish(params, seed);
      if (r['error'] != null && mounted) {
        setState(() => _error = '${r['error']}');
      }
      await _load(); // the new face joins the listing
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _publishing = false);
    }
  }

  Future<void> _wear(String eid) async {
    try {
      final face = await widget.client.typefaceFace(eid);
      final b64 = '${face['ttf_b64'] ?? ''}';
      if (b64.isEmpty) {
        setState(() => _error = 'that face carries no font bytes');
        return;
      }
      final family = 'GalleryFace-$eid';
      if (!_loaded.contains(family)) {
        await loadFontFamily(family, base64Decode(b64));
        _loaded.add(family);
      }
      if (mounted) setState(() => _wornFamily = family);
    } catch (e) {
      if (mounted) setState(() => _error = 'wear failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return HairlineCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          FilledButton.tonal(
            onPressed: (widget.benchFace == null || _publishing)
                ? null
                : _publish,
            child: Text(_publishing ? 'Publishing…' : 'Publish this face'),
          ),
          const SizedBox(width: FwLayout.s3),
          OutlinedButton(
              onPressed: _loading ? null : _load,
              child: Text(_loading ? 'Loading…' : 'Refresh')),
          const Spacer(),
          Text('${_faces.length} in the gallery',
              style: fwMono(t, size: 10.5, color: t.inkFaint)),
        ]),
        if (_error != null) ...[
          const SizedBox(height: FwLayout.s2),
          HonestNull(_error!),
        ],
        if (_faces.isEmpty && !_loading) ...[
          const SizedBox(height: FwLayout.s2),
          Text('No faces published yet. Mint one above and publish it.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
        ],
        for (final f in _faces) _faceRow(t, f),
      ]),
    );
  }

  Widget _faceRow(FwTokens t, Map<String, dynamic> f) {
    final eid = '${f['eid']}';
    final worn = _wornFamily == 'GalleryFace-$eid';
    final w = (f['params'] is Map) ? (f['params'] as Map)['weight'] : null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(children: [
        SizedBox(
          width: 220,
          child: Text('the quick brown fox 0123',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontFamily: worn ? 'GalleryFace-$eid' : null,
                  fontSize: 15,
                  color: t.ink)),
        ),
        const SizedBox(width: FwLayout.s3),
        Text('${f['family'] ?? ''} · seed ${f['seed']}'
            '${w != null ? ' · w${w.toStringAsFixed(3)}' : ''}',
            style: fwMono(t, size: 10.5, color: t.inkMuted)),
        const Spacer(),
        HashText('mint', '${f['mint_id']}', keep: 16),
        const SizedBox(width: FwLayout.s2),
        TextButton(
            onPressed: () => _wear(eid),
            child: Text(worn ? 'worn' : 'wear',
                style: fwMono(t, size: 10.5,
                    color: worn ? t.verified : t.inkMuted))),
      ]),
    );
  }
}
