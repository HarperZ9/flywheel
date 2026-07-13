// fw.dart — the shared component grammar of the Flywheel surface.
//
// Every view composes from these: kickers (mono uppercase section voice),
// verdict pills (the only colored chips), hairline cards (panel tint + 1px
// line, no shadow), honest-null notes (drift-tinted callouts), hash text
// (selectable mono provenance), and stat tiles.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';

/// Mono uppercase section label. Drift color marks the view's one hot
/// section; default is faint ink.
class Kicker extends StatelessWidget {
  final String text;
  final bool hot;
  const Kicker(this.text, {super.key, this.hot = false});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Text(text.toUpperCase(),
        style: fwKicker(t, color: hot ? t.drift : t.inkFaint));
  }
}

/// A verdict chip: tinted ground, hairline border, mono uppercase label.
/// The ONLY colored chip in the system; `status` maps through the verdict
/// palette (verified / drift / unverifiable).
class VerdictPill extends StatelessWidget {
  final String label;
  final String status;
  const VerdictPill(this.label, {super.key, required this.status});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final c = t.statusColor(status);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: c.withValues(alpha: 0.35)),
      ),
      child: Text(label.toUpperCase(),
          style: fwKicker(t, color: c, size: 10).copyWith(letterSpacing: 1.4)),
    );
  }
}

/// A small verdict dot for dense rows.
class VerdictDot extends StatelessWidget {
  final String status;
  final double size;
  const VerdictDot(this.status, {super.key, this.size = 8});

  @override
  Widget build(BuildContext context) {
    final c = context.fw.statusColor(status);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: c, shape: BoxShape.circle),
    );
  }
}

/// Panel-tinted card with a 1px hairline. Never glass, never elevation.
class HairlineCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final bool recessed;
  const HairlineCard(
      {super.key,
      required this.child,
      this.padding = const EdgeInsets.all(FwLayout.s4),
      this.recessed = false});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: recessed ? t.ground2 : t.panel,
        borderRadius: BorderRadius.circular(FwLayout.radius),
        border: Border.all(color: t.line),
      ),
      child: child,
    );
  }
}

/// The honest-null note: drift-tinted callout that keeps a negative or
/// bounded result visible instead of hiding it.
class HonestNull extends StatelessWidget {
  final String text;
  const HonestNull(this.text, {super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: FwLayout.s4, vertical: FwLayout.s3),
      decoration: BoxDecoration(
        color: t.drift.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        border: Border.all(color: t.drift.withValues(alpha: 0.42)),
      ),
      child: Text(text,
          style: TextStyle(color: t.inkSoft, fontSize: 12.5, height: 1.45)),
    );
  }
}

/// Selectable mono provenance line: a label and a hash (shortened for
/// display, full value selectable).
class HashText extends StatelessWidget {
  final String label;
  final String hash;
  final int keep;
  const HashText(this.label, this.hash, {super.key, this.keep = 24});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final short = hash.length > keep ? '${hash.substring(0, keep)}…' : hash;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: fwMono(t, size: 11.5, color: t.inkFaint)),
        const SizedBox(width: FwLayout.s2),
        Flexible(
          child: SelectableText(short,
              maxLines: 1,
              style: fwMono(t, size: 12, weight: FontWeight.w600)),
        ),
      ],
    );
  }
}

/// A stat tile: mono kicker over a large weight-700 value, optional verdict
/// coloring on the value.
class StatTile extends StatelessWidget {
  final String label;
  final String value;
  final String? status;
  const StatTile(
      {super.key, required this.label, required this.value, this.status});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final valueColor = status == null ? t.ink : t.statusColor(status!);
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Kicker(label),
          const SizedBox(height: FwLayout.s2),
          Text(value,
              style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                  height: 1.05,
                  color: valueColor,
                  fontFeatures: const [FontFeature.tabularFigures()])),
        ],
      ),
    );
  }
}

/// Section header: title plus optional trailing action.
class SectionHeader extends StatelessWidget {
  final String title;
  final Widget? trailing;
  final String? kicker;
  const SectionHeader(this.title, {super.key, this.trailing, this.kicker});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (kicker != null) ...[
                Kicker(kicker!),
                const SizedBox(height: FwLayout.s1),
              ],
              Text(title, style: Theme.of(context).textTheme.titleLarge),
            ],
          ),
        ),
        if (trailing != null) trailing!,
      ],
    );
  }
}

/// The standard view scaffold: padded scrollable column with a header.
class ViewScroll extends StatelessWidget {
  final List<Widget> children;
  const ViewScroll({super.key, required this.children});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.symmetric(
          horizontal: FwLayout.s6, vertical: FwLayout.s5),
      children: children,
    );
  }
}

/// Empty / offline state. States the fact plainly and shows the command
/// that changes it. No decoration.
class FwEmpty extends StatelessWidget {
  final String message;
  final String? command;
  const FwEmpty(this.message, {super.key, this.command});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(message,
              style: TextStyle(color: t.inkMuted, fontSize: 13.5),
              textAlign: TextAlign.center),
          if (command != null) ...[
            const SizedBox(height: FwLayout.s3),
            Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: FwLayout.s3, vertical: FwLayout.s2),
              decoration: BoxDecoration(
                color: t.ground2,
                borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
                border: Border.all(color: t.line),
              ),
              child: SelectableText(command!, style: fwMono(t, size: 12.5)),
            ),
          ],
        ],
      ),
    );
  }
}
