// side_rail.dart — the navigation sidebar. Collapsible so the working
// surface stays the largest thing on screen: full shows numbered labels,
// collapsed shows a thin mono-code rail. Denser rows, trimmer chrome.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import 'aperture.dart';

class RailDestination {
  final String label;
  final String abbr;

  /// The goal group this destination belongs to (Start / Do / Know / Advanced).
  /// The rail draws a section header when the group changes, so the nav reads as
  /// "what did you come to do", not a flat wall of subsystems.
  final String group;
  const RailDestination(this.label, {this.abbr = '', this.group = ''});
  String get code => abbr.isNotEmpty
      ? abbr
      : (label.length >= 2 ? label.substring(0, 2) : label).toUpperCase();
}

class SideRail extends StatelessWidget {
  final List<RailDestination> destinations;
  final int selectedIndex;
  final ValueChanged<int> onSelect;
  final ThemeMode themeMode;
  final VoidCallback onToggleTheme;
  final bool collapsed;
  final VoidCallback onToggleCollapse;
  final VoidCallback? onOpenAppearance;

  const SideRail({
    super.key,
    required this.destinations,
    required this.selectedIndex,
    required this.onSelect,
    required this.themeMode,
    required this.onToggleTheme,
    required this.collapsed,
    required this.onToggleCollapse,
    this.onOpenAppearance,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return AnimatedContainer(
      duration: FwLayout.transition,
      width: collapsed ? 52 : 172,
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(right: BorderSide(color: t.line)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(t),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: FwLayout.s1),
              children: [
                for (var i = 0; i < destinations.length; i++) ...[
                  if (_startsGroup(i)) ...[
                    if (collapsed)
                      Container(
                        height: 1,
                        margin: const EdgeInsets.fromLTRB(
                            FwLayout.s3, FwLayout.s3, FwLayout.s3, FwLayout.s2),
                        color: t.hairline,
                      )
                    else
                      _GroupHeader(destinations[i].group, first: i == 0),
                  ],
                  _RailItem(
                    index: i,
                    dest: destinations[i],
                    selected: i == selectedIndex,
                    collapsed: collapsed,
                    onTap: () => onSelect(i),
                  ),
                ],
              ],
            ),
          ),
          _footer(t),
        ],
      ),
    );
  }

  bool _startsGroup(int i) =>
      destinations[i].group.isNotEmpty &&
      (i == 0 || destinations[i - 1].group != destinations[i].group);

  Widget _header(FwTokens t) {
    return Padding(
      padding: EdgeInsets.symmetric(
          horizontal: collapsed ? FwLayout.s2 : FwLayout.s3,
          vertical: FwLayout.s3),
      child: Row(
        mainAxisAlignment:
            collapsed ? MainAxisAlignment.center : MainAxisAlignment.start,
        children: [
          const ApertureMark(size: 26),
          if (!collapsed) ...[
            const SizedBox(width: FwLayout.s2),
            Expanded(
              child: Text('Flywheel',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w700,
                      color: t.ink)),
            ),
            _iconBtn(t, Icons.chevron_left, onToggleCollapse),
          ],
        ],
      ),
    );
  }

  Widget _footer(FwTokens t) {
    if (collapsed) {
      return Padding(
        padding: const EdgeInsets.all(FwLayout.s2),
        child: Column(
          children: [
            _iconBtn(t, Icons.chevron_right, onToggleCollapse),
            const SizedBox(height: FwLayout.s2),
            _iconBtn(t, _themeIcon, onToggleTheme),
            if (onOpenAppearance != null) ...[
              const SizedBox(height: FwLayout.s2),
              _iconBtn(t, Icons.tune, onOpenAppearance!),
            ],
          ],
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.all(FwLayout.s2),
      child: Row(
        children: [
          Expanded(
              child: _ThemeToggle(mode: themeMode, onToggle: onToggleTheme)),
          if (onOpenAppearance != null) ...[
            const SizedBox(width: FwLayout.s2),
            _iconBtn(t, Icons.tune, onOpenAppearance!),
          ],
        ],
      ),
    );
  }

  IconData get _themeIcon => switch (themeMode) {
        ThemeMode.light => Icons.light_mode_outlined,
        ThemeMode.dark => Icons.dark_mode_outlined,
        ThemeMode.system => Icons.contrast,
      };

  Widget _iconBtn(FwTokens t, IconData icon, VoidCallback onTap) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Icon(icon, size: 15, color: t.inkFaint),
        ),
      ),
    );
  }
}

class _RailItem extends StatefulWidget {
  final int index;
  final RailDestination dest;
  final bool selected;
  final bool collapsed;
  final VoidCallback onTap;
  const _RailItem(
      {required this.index,
      required this.dest,
      required this.selected,
      required this.collapsed,
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
    final bg = selected
        ? t.panel
        : _hover
            ? t.panel.withValues(alpha: 0.5)
            : Colors.transparent;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: Tooltip(
        message: widget.collapsed ? widget.dest.label : '',
        waitDuration: const Duration(milliseconds: 400),
        child: GestureDetector(
          onTap: widget.onTap,
          behavior: HitTestBehavior.opaque,
          child: Container(
            margin: const EdgeInsets.symmetric(
                horizontal: FwLayout.s1, vertical: 1),
            padding: EdgeInsets.symmetric(
                horizontal: widget.collapsed ? 0 : FwLayout.s2, vertical: 6),
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
            ),
            child: widget.collapsed
                ? _compact(t, selected)
                : _full(t, selected),
          ),
        ),
      ),
    );
  }

  Widget _compact(FwTokens t, bool selected) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: 2.5,
          height: 14,
          decoration: BoxDecoration(
            color: selected ? t.ink : Colors.transparent, // selection = ink emphasis, not a verdict
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: 4),
        Text(widget.dest.code,
            style: fwKicker(t,
                size: 9.5, color: selected ? t.ink : t.inkMuted)),
      ],
    );
  }

  Widget _full(FwTokens t, bool selected) {
    return Row(
      children: [
        Container(
          width: 2.5,
          height: 13,
          decoration: BoxDecoration(
            color: selected ? t.ink : Colors.transparent, // selection = ink emphasis, not a verdict
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: FwLayout.s2),
        Expanded(
          child: Text(widget.dest.label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                  color: selected ? t.ink : t.inkMuted)),
        ),
      ],
    );
  }
}

class _GroupHeader extends StatelessWidget {
  final String label;
  final bool first;
  const _GroupHeader(this.label, {this.first = false});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Padding(
      padding: EdgeInsets.fromLTRB(
          FwLayout.s3, first ? FwLayout.s2 : FwLayout.s4, FwLayout.s3, 5),
      child: Text(label.toUpperCase(),
          style: fwKicker(t, size: 9, color: t.inkFaint)),
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
              horizontal: FwLayout.s2, vertical: 6),
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
                    style: fwMono(t, size: 10, color: t.inkMuted)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
