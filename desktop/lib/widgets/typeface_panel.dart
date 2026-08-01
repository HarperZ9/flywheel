// typeface_panel.dart — the forge's front: eight parameters, a seed, and a
// mint that can refuse. The specimen paints from the minted outlines with
// nonzero winding, so what you see is the artifact, not a preview of one.
// Wear-it loads the minted font file into THIS app's registry, so your
// own text renders in your own face seconds after it exists.

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

typedef MintFace = Future<Map<String, dynamic>> Function(
    Map<String, dynamic> params, int seed);
typedef LoadFont = Future<void> Function(String family, Uint8List bytes);

/// Register a TrueType font under a family name so widgets can render with it.
/// Shared so the gallery card can wear a fetched face the same way the forge
/// wears a freshly minted one.
Future<void> loadFontFamily(String family, Uint8List bytes) async {
  final loader = FontLoader(family)
    ..addFont(Future.value(ByteData.view(bytes.buffer)));
  await loader.load();
}

Future<void> _defaultLoadFont(String family, Uint8List bytes) =>
    loadFontFamily(family, bytes);

class TypefacePanel extends StatefulWidget {
  final MintFace onMint;
  final LoadFont? fontLoad;

  /// Fires with the exact params of a successful mint so sibling panels
  /// (poster, brand kit) can wear the minted face for real.
  final ValueChanged<Map<String, dynamic>>? onMinted;
  const TypefacePanel(
      {super.key, required this.onMint, this.fontLoad, this.onMinted});

  @override
  State<TypefacePanel> createState() => _TypefacePanelState();
}

class _TypefacePanelState extends State<TypefacePanel> {
  final Map<String, double> _p = {
    'x_height': 0.50,
    'weight': 0.085,
    'contrast': 0.82,
    'width': 1.0,
    'roundness': 2.4,
    'aperture': 0.6,
  };
  static const _ranges = {
    'x_height': (0.44, 0.60),
    'weight': (0.05, 0.16),
    'contrast': (0.45, 1.0),
    'width': (0.75, 1.25),
    'roundness': (1.6, 3.2),
    'aperture': (0.2, 1.0),
  };
  int _seed = 58;
  Map<String, dynamic>? _face;
  bool _minting = false, _wearing = false;
  String? _error, _wornFamily;
  final _wearText = TextEditingController(
      text: 'the quick brown fox jumps over the lazy dog 0123456789');
  static final Set<String> _loadedFamilies = {};

  @override
  void dispose() {
    _wearText.dispose();
    super.dispose();
  }

  Future<void> _wear() async {
    final face = _face;
    final b64 = face?['ttf_b64'];
    final mintId = '${face?['receipt']?['mint_id'] ?? ''}';
    if (b64 == null || mintId.isEmpty || _wearing) return;
    setState(() => _wearing = true);
    try {
      // one registry family per distinct mint, so switching seeds switches
      // the rendered face instead of piling bytes under one name
      final family = 'ZentropyMint-$mintId';
      if (!_loadedFamilies.contains(family)) {
        await (widget.fontLoad ?? _defaultLoadFont)(
            family, base64Decode('$b64'));
        _loadedFamilies.add(family);
      }
      if (mounted) setState(() => _wornFamily = family);
    } catch (e) {
      if (mounted) setState(() => _error = 'wear failed: $e');
    } finally {
      if (mounted) setState(() => _wearing = false);
    }
  }

  Future<void> _mint() async {
    if (_minting) return;
    setState(() {
      _minting = true;
      _error = null;
    });
    try {
      final r = await widget.onMint(Map<String, dynamic>.from(_p), _seed);
      if (mounted) setState(() => _face = r);
      if (r['refused'] != true && r['error'] == null) {
        widget.onMinted?.call({...Map<String, dynamic>.from(_p), 'seed': _seed});
      }
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _minting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final face = _face;
    final refused = face?['refused'] == true;
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Mint a face',
              style:
                  const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
          const SizedBox(height: FwLayout.s2),
          Text(
              'Eight parameters and a seed expand fixed skeletons through a '
              'pen. The legibility rules can refuse the mint, and the '
              'receipt makes the design re-derivable.',
              style: TextStyle(fontSize: 12.5, color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          for (final e in _ranges.entries) _slider(t, e.key, e.value),
          Row(children: [
            Text('seed', style: fwMono(t, size: 11.5, color: t.inkFaint)),
            const SizedBox(width: FwLayout.s3),
            SizedBox(
              width: 90,
              child: TextField(
                controller: TextEditingController(text: '$_seed'),
                style: fwMono(t, size: 12.5),
                keyboardType: TextInputType.number,
                onSubmitted: (v) =>
                    setState(() => _seed = int.tryParse(v) ?? _seed),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            FilledButton(
              onPressed: _minting ? null : _mint,
              child: Text(_minting ? 'Minting…' : 'Mint'),
            ),
          ]),
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s3),
            HonestNull('Failed: $_error'),
          ],
          if (face != null && refused) ...[
            const SizedBox(height: FwLayout.s3),
            for (final r in (face['refusals'] as List? ?? const []))
              HonestNull('$r'),
          ],
          if (face != null && !refused) ...[
            const SizedBox(height: FwLayout.s4),
            SizedBox(
              height: 130,
              width: double.infinity,
              // the painter must never bleed past its box: clip it
              child: ClipRect(
                child: CustomPaint(
                  painter: SpecimenPainter(
                      face['glyphs'] as Map<String, dynamic>? ?? const {},
                      (face['metrics']?['x_height'] as num?)?.toDouble() ??
                          500,
                      t.ink),
                ),
              ),
            ),
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              const VerdictPill('minted', status: 'verified'),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: HashText(
                    'mint', '${face['receipt']?['mint_id'] ?? ''}', keep: 16),
              ),
              if (face['ttf_b64'] != null)
                OutlinedButton(
                  onPressed: _wearing ? null : _wear,
                  child: Text(_wearing ? 'Loading…' : 'Wear it'),
                ),
            ]),
            if (_wornFamily != null) ...[
              const SizedBox(height: FwLayout.s3),
              Row(children: [
                const VerdictPill('wearing it', status: 'verified'),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                  child: Text(
                      'this text renders from the font file the forge just '
                      'wrote, loaded into this app live',
                      style: fwMono(t, size: 11).copyWith(color: t.inkMuted)),
                ),
              ]),
              const SizedBox(height: FwLayout.s2),
              TextField(
                controller: _wearText,
                maxLines: 2,
                style: TextStyle(
                    fontFamily: _wornFamily, fontSize: 30, color: t.ink),
                decoration: const InputDecoration(
                    hintText: 'type anything; lowercase and digits carry '
                        'the face'),
              ),
            ],
          ],
        ],
      ),
    );
  }

  Widget _slider(FwTokens t, String key, (double, double) range) {
    return Row(children: [
      SizedBox(
        width: 84,
        child: Text(key.replaceAll('_', ' '),
            style: fwMono(t, size: 11, color: t.inkFaint)),
      ),
      Expanded(
        child: Slider(
          value: _p[key]!.clamp(range.$1, range.$2),
          min: range.$1,
          max: range.$2,
          onChanged: (v) => setState(() => _p[key] = v),
          onChangeEnd: (_) => _mint(),
        ),
      ),
      SizedBox(
        width: 48,
        child: Text(_p[key]!.toStringAsFixed(3),
            style: fwMono(t, size: 11, color: t.inkMuted)),
      ),
    ]);
  }
}

/// Paints the proving word from raw minted contours: nonzero winding, so
/// strokes weld and counters carve exactly as the engine intended.
class SpecimenPainter extends CustomPainter {
  final Map<String, dynamic> glyphs;
  final double xHeight;
  final Color ink;
  SpecimenPainter(this.glyphs, this.xHeight, this.ink);

  @override
  void paint(Canvas canvas, Size size) {
    if (glyphs.isEmpty) return;
    const word = 'adhesion';
    double adv = 0;
    for (final ch in word.split('')) {
      final g = glyphs[ch];
      if (g is Map) adv += (g['advance'] as num?)?.toDouble() ?? 0;
    }
    if (adv == 0) return;
    final scale = size.width / (adv + 80);
    final base = size.height * 0.88;
    final paint = Paint()..color = ink;
    double x = 40 * scale;
    for (final ch in word.split('')) {
      final g = glyphs[ch];
      if (g is! Map) continue;
      final path = Path()..fillType = PathFillType.nonZero;
      for (final ring in (g['contours'] as List? ?? const [])) {
        final pts = <Offset>[
          for (final p in (ring as List))
            Offset(x + (p[0] as num) * scale,
                base - (p[1] as num) * scale)
        ];
        if (pts.length > 2) path.addPolygon(pts, true);
      }
      canvas.drawPath(path, paint);
      x += ((g['advance'] as num?)?.toDouble() ?? 0) * scale;
    }
  }

  @override
  bool shouldRepaint(SpecimenPainter old) =>
      old.glyphs != glyphs || old.ink != ink;
}
