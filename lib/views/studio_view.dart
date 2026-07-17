// studio_view.dart — the Studio: creation with provenance. The art plate is
// a seeded flow-field kernel (the seed is recorded on the plate, so every
// image is reproducible); the schematic draws the verified loop from live
// state; the music lane is declared with an honest null, not faked.
//
// The spectrum band is allowed HERE and only here: generative art is the
// one surface where color is the subject rather than a verdict.

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/gateway_models.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/aperture.dart';
import '../widgets/brand_kit_panel.dart';
import '../widgets/forge_panel.dart';
import '../widgets/harmonograph_panel.dart';
import '../widgets/fw.dart';
import '../widgets/graph_editor.dart';
import '../widgets/graph_panel.dart';
import '../widgets/pipeline_panel.dart';
import '../widgets/poster_panel.dart';
import '../widgets/raster_fx_panel.dart';
import '../widgets/sound_panel.dart';
import '../widgets/typeface_panel.dart';

class StudioView extends StatefulWidget {
  final WorldDoc? world;
  final LaneRoster? roster;
  final bool alive;
  final GatewayClient? client;
  const StudioView(
      {super.key, this.world, this.roster, required this.alive, this.client});

  @override
  State<StudioView> createState() => _StudioViewState();
}

class _StudioViewState extends State<StudioView> {
  int _seed = kApertureSeed;

  /// The last successful mint's params; poster and brand kit wear it.
  Map<String, dynamic>? _mintedFace;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return ViewScroll(
      storageKey: 'studio',
      children: [
        const SectionHeader('Studio', kicker: 'creation with provenance'),
        const SizedBox(height: FwLayout.s3),
        Text(
          'Every plate is seeded and reproducible: the seed on the mark IS '
          'the provenance. Schematics draw from live state, never from a '
          'stale diagram.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: FwLayout.s4),
        const Kicker('field plate · seeded kernel', hot: true),
        const SizedBox(height: FwLayout.s3),
        HairlineCard(
          padding: EdgeInsets.zero,
          child: Column(
            children: [
              ClipRRect(
                borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(FwLayout.radius)),
                child: SizedBox(
                  height: 260,
                  width: double.infinity,
                  child: RepaintBoundary(
                    child: CustomPaint(
                      painter: _FieldPainter(seed: _seed, ground: t.ground2),
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: FwLayout.s4, vertical: FwLayout.s3),
                child: Row(
                  children: [
                    Text('flywheel field kernel · seed $_seed',
                        style: fwMono(t, size: 11, color: t.inkMuted)),
                    const Spacer(),
                    OutlinedButton(
                      onPressed: () => setState(() =>
                          _seed = (_seed * 48271 + 11) % 100000),
                      child: const Text('New seed'),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: FwLayout.s5),
        const Kicker('the loop · drawn from live state'),
        const SizedBox(height: FwLayout.s3),
        _loopSchematic(context),
        if (widget.client != null) ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('typeface forge · parametric type'),
          const SizedBox(height: FwLayout.s3),
          TypefacePanel(
            onMint: (params, seed) =>
                widget.client!.typefaceMint(params, seed),
            onMinted: (params) => setState(() => _mintedFace = params),
          ),
          const SizedBox(height: FwLayout.s5),
          Kicker(_mintedFace == null
              ? 'poster composer · mint a face above and the plate wears it'
              : 'poster composer · the plate wears your minted face'),
          const SizedBox(height: FwLayout.s3),
          PosterPanel(client: widget.client!, faceParams: _mintedFace),
          const SizedBox(height: FwLayout.s5),
          const Kicker('telos engine · the plotter kernel, driven in place'),
          const SizedBox(height: FwLayout.s3),
          HarmonographPanel(client: widget.client!),
          const SizedBox(height: FwLayout.s5),
          const Kicker('telos engine · raster kernels over the plate'),
          const SizedBox(height: FwLayout.s3),
          RasterFxPanel(client: widget.client!),
          const SizedBox(height: FwLayout.s5),
          const Kicker('the creative line · stages that chain'),
          const SizedBox(height: FwLayout.s3),
          PipelinePanel(client: widget.client!),
          const SizedBox(height: FwLayout.s5),
          const Kicker('the creative graph · branches that testify'),
          const SizedBox(height: FwLayout.s3),
          GraphPanel(client: widget.client!),
          const SizedBox(height: FwLayout.s3),
          const Kicker('the node canvas · author a graph by hand'),
          const SizedBox(height: FwLayout.s3),
          GraphEditor(client: widget.client!),
          const SizedBox(height: FwLayout.s5),
          const Kicker('brand kit · one seed, a whole identity'),
          const SizedBox(height: FwLayout.s3),
          BrandKitPanel(client: widget.client!, faceParams: _mintedFace),
          const SizedBox(height: FwLayout.s5),
          const Kicker('prompt forge · a goal becomes a gated prompt'),
          const SizedBox(height: FwLayout.s3),
          ForgePanel(client: widget.client!),
          const SizedBox(height: FwLayout.s5),
          const Kicker('music · the seeded chime study'),
          const SizedBox(height: FwLayout.s3),
          SoundPanel(client: widget.client!),
        ] else ...[
          const SizedBox(height: FwLayout.s5),
          const Kicker('music'),
          const SizedBox(height: FwLayout.s3),
          const HonestNull(
              'The engine is offline; the chime study composes when it runs.'),
        ],
      ],
    );
  }

  Widget _loopSchematic(BuildContext context) {
    final t = context.fw;
    final live = widget.roster?.byStatus['live'] ?? 0;
    final total = widget.roster?.nLanes ?? 0;
    final measured = widget.world?.findings['measured'] ?? 0;
    final root = widget.world?.rootHash ?? '';
    final stages = [
      ('propose', 'any endpoint'),
      ('verify', 'the oracle disposes'),
      ('receipt', '$measured measured'),
      ('memory', 'folded, recallable'),
      ('context', '$live/$total lanes live'),
    ];
    if (!widget.alive) {
      return const HonestNull(
          'The engine is offline, so the schematic has no live state to '
          'draw. Start it and the numbers appear.');
    }
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 0,
            runSpacing: FwLayout.s2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              for (var i = 0; i < stages.length; i++) ...[
                _stageBox(t, stages[i].$1, stages[i].$2),
                if (i < stages.length - 1)
                  Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: FwLayout.s2),
                    child: Text('→',
                        style: TextStyle(color: t.inkFaint, fontSize: 14)),
                  ),
              ],
            ],
          ),
          if (root.isNotEmpty) ...[
            const SizedBox(height: FwLayout.s3),
            HashText('world', root, keep: 24),
          ],
        ],
      ),
    );
  }

  Widget _stageBox(FwTokens t, String name, String detail) {
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: FwLayout.s3, vertical: FwLayout.s2),
      decoration: BoxDecoration(
        color: t.ground2,
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: t.line),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(name,
              style: TextStyle(
                  fontSize: 12.5, fontWeight: FontWeight.w600, color: t.ink)),
          Text(detail, style: fwMono(t, size: 10, color: t.inkFaint)),
        ],
      ),
    );
  }
}

/// Plotter-thin flow-field arcs banded across the spectrum. Deterministic
/// from the seed; the same seed always draws the same plate.
class _FieldPainter extends CustomPainter {
  final int seed;
  final Color ground;
  _FieldPainter({required this.seed, required this.ground});

  // The spectrum band from the inspiration corpus: art-only colors.
  static const _band = [
    Color(0xFFC2447F), // magenta
    Color(0xFFC96F3A), // ember
    Color(0xFFC9A23A), // gold
    Color(0xFF6FA33C), // lime
    Color(0xFF3A9FA8), // cyan
    Color(0xFF6C5CE0), // iris
  ];

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = ground);
    final rng = Mulberry32(seed);
    final cx = size.width * (0.25 + 0.5 * rng.next());
    final cy = size.height * (0.3 + 0.4 * rng.next());
    final k1 = 1.5 + rng.next() * 2.5;
    final k2 = 0.8 + rng.next() * 1.8;
    const arcs = 130;
    for (var i = 0; i < arcs; i++) {
      var x = size.width * rng.next();
      var y = size.height * rng.next();
      final color = _band[i % _band.length];
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.7
        ..color = color.withValues(alpha: 0.30 + 0.30 * rng.next());
      final path = Path()..moveTo(x, y);
      for (var s = 0; s < 64; s++) {
        final dx = x - cx, dy = y - cy;
        final r = math.sqrt(dx * dx + dy * dy) + 1e-6;
        final angle = math.atan2(dy, dx) +
            math.pi / 2 +
            0.6 * math.sin(k1 * r / size.width * math.pi) +
            0.3 * math.cos(k2 * x / size.width * math.pi);
        x += math.cos(angle) * 3.2;
        y += math.sin(angle) * 3.2;
        if (x < -20 || y < -20 || x > size.width + 20 || y > size.height + 20) {
          break;
        }
        path.lineTo(x, y);
      }
      canvas.drawPath(path, paint);
    }
  }

  @override
  bool shouldRepaint(_FieldPainter old) =>
      old.seed != seed || old.ground != ground;
}
