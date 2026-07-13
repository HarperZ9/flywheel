// side_rail.dart — the navigation sidebar: aperture mark, wordmark, numbered
// destinations, theme toggle. Ink on calm ground; the selected view carries
// the single drift bar.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'aperture.dart';

class RailDestination {
  final String label;
  const RailDestination(this.label);
}

class SideRail extends StatelessWidget {
  final List<RailDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelect;
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;

  const SideRail({
    super.key,
    required this.destinations,
    required this.selectedIndex,
    required this.onSelect,
    required this.themeMode,
    required this.onToggleTheme,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      width: 192,
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(right: BorderSide(color: t.line)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
                FwLayout.s4, FwLayout.s5, FwLayout.s4, FwLayout.s5),
            child: Row(
              children: [
                const ApertureMark(size: 30),
                const SizedBox(width: FwLayout.s3),
                Flexible(
                  child: Text('Flywheel',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontSize: 15.5,
                          fontWeight: FontWeight.w700,
                          color: t.ink)),
                ),
              ],
            ),
          ),
          for (var i = 0; i < destinations.length; i++)
            _RailItem(
              index: i,
              label: destinations[i].label,
              selected: i == selectedIndex,
              onTap: () => onSelect(i),
            ),
          const Spacer(),
          Padding(
            padding: const EdgeInsets.all(FwLayout.s3),
            child: _ThemeToggle(mode: themeMode, onToggle: onToggleTheme),
          ),
        ],
      ),
    );
  }
}

class _RailItem extends StatefulWidget {
  final int index;
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _RailItem(
      {required this.index,
      required this.label,
      required this.selected,
      required this.onTap});

  @override
  State<_RailItem> createState() => _RailItemState();
}

class _RailItemState extends State<_RailItem> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final selected = widget.selected;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        onTap: widget.onTap,
        behavior: HitTestBehavior.opaque,
        child: AnimatedContainer(
          duration: FwLayout.transition,
          margin: const EdgeInsets.symmetric(horizontal: FwLayout.s2),
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s3, vertical: FwLayout.s2 + 2),
          decoration: BoxDecoration(
            color: selected
                ? t.panel
                : _hover
                    ? t.panel.withValues(alpha: 0.5)
                    : Colors.transparent,
            borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
            border: Border.all(
                color: selected ? t.line : Colors.transparent),
          ),
          child: Row(
            children: [
              Container(
                width: 2.5,
                height: 14,
                decoration: BoxDecoration(
                  color: selected ? t.drift : Colors.transparent,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(width: FwLayout.s3),
              Text('0${widget.index + 1}',
                  style: fwKicker(t,
                      size: 9.5,
                      color: selected ? t.inkMuted : t.inkFaint)),
              const SizedBox(width: FwLayout.s3),
              Expanded(
                child: Text(widget.label,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 13.5,
                        fontWeight:
                            selected ? FontWeight.w600 : FontWeight.w500,
                        color: selected ? t.ink : t.inkMuted)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ThemeToggle extends StatelessWidget {
  final ThemeMode mode;
  final VoidCallback onToggle;
  const _ThemeToggle({required this.mode, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final label = switch (mode) {
      ThemeMode.system => 'theme: system',
      ThemeMode.light => 'theme: light',
      ThemeMode.dark => 'theme: dark',
    };
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onToggle,
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: FwLayout.s3, vertical: FwLayout.s2),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
            border: Border.all(color: t.line),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                  switch (mode) {
                    ThemeMode.light => Icons.light_mode_outlined,
                    ThemeMode.dark => Icons.dark_mode_outlined,
                    ThemeMode.system => Icons.contrast,
                  },
                  size: 13,
                  color: t.inkMuted),
              const SizedBox(width: FwLayout.s2),
              Flexible(
                child: Text(label,
                    overflow: TextOverflow.ellipsis,
                    style: fwMono(t, size: 10.5, color: t.inkMuted)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
