// shell_rail.dart -- the shell's navigation rail: search field, the five
// catalog groups, theme and appearance actions, and the keyboard-adjustable
// resize handle. The search query is rail-local state; typing re-filters
// the groups immediately.
import 'package:flutter/material.dart';

import '../accessibility/accessible_action.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../theme/flywheel_theme.dart';
import 'nav_group.dart';
import 'nav_search_field.dart';
import 'rail_resizer.dart';

class ShellRail extends StatefulWidget {
  final bool collapsed;
  final double width;
  final bool inDrawer;
  final DestinationId selected;
  final ValueChanged<DestinationId> onGo;
  final ValueChanged<double> onResize;
  final VoidCallback onToggleCollapse;
  final VoidCallback onToggleTheme;
  final VoidCallback onOpenAppearance;
  final VoidCallback onOpenRecovery;

  /// Opens the gateway-pairing panel. Optional so hand-built rails in tests keep
  /// compiling; the action renders only when a handler is supplied.
  final VoidCallback? onOpenConnection;

  /// Opens the sessions view (your resumable work, on any device). Optional for
  /// the same reason; renders only when supplied.
  final VoidCallback? onOpenSessions;

  /// Opens the assistant (ask for work, or a device action). Optional; renders
  /// only when supplied.
  final VoidCallback? onOpenAssistant;

  const ShellRail({
    super.key,
    required this.collapsed,
    required this.width,
    this.inDrawer = false,
    required this.selected,
    required this.onGo,
    required this.onResize,
    required this.onToggleCollapse,
    required this.onToggleTheme,
    required this.onOpenAppearance,
    required this.onOpenRecovery,
    this.onOpenConnection,
    this.onOpenSessions,
    this.onOpenAssistant,
  });

  @override
  State<ShellRail> createState() => _ShellRailState();
}

class _ShellRailState extends State<ShellRail> {
  final TextEditingController _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final q = _query.trim().toLowerCase();
    bool matches(DestinationSpec spec) =>
        q.isEmpty || spec.label.toLowerCase().contains(q);
    final groups = <String, List<DestinationSpec>>{};
    for (final spec in destinationCatalog) {
      if (matches(spec)) (groups[spec.group.name] ??= []).add(spec);
    }
    final rail = AnimatedContainer(
      duration: Duration.zero,
      width: widget.collapsed ? 52.0 : widget.width.clamp(148.0, 320.0),
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(right: BorderSide(color: t.line)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(context),
          if (!widget.collapsed)
            NavSearchField(
              controller: _search,
              onChanged: (value) => setState(() => _query = value),
            ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 4),
              children: [
                for (final entry in groups.entries)
                  NavGroup(
                    label: entry.key,
                    destinations: entry.value,
                    selected: widget.selected,
                    collapsed: widget.collapsed,
                    foldable: widget.inDrawer,
                    onSelect: widget.onGo,
                  ),
                if (groups.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: Text('No destination matches.',
                        style: TextStyle(fontSize: 12, color: t.inkFaint)),
                  ),
              ],
            ),
          ),
          _footer(context),
        ],
      ),
    );
    if (widget.collapsed) return rail;
    return Stack(children: [
      rail,
      Positioned(
        right: 0,
        top: 0,
        bottom: 0,
        width: 6,
        child: RailResizer(
            width: widget.width.clamp(148.0, 320.0),
            onResize: widget.onResize),
      ),
    ]);
  }

  Widget _header(BuildContext context) {
    final t = context.fw;
    return Padding(
      padding: EdgeInsets.symmetric(
          horizontal: widget.collapsed ? 8 : 12, vertical: 12),
      child: Row(
        mainAxisAlignment: widget.collapsed
            ? MainAxisAlignment.center
            : MainAxisAlignment.start,
        children: [
          if (!widget.collapsed) ...[
            Expanded(
              child: Text('Flywheel',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w700,
                      color: t.ink)),
            ),
            AccessibleAction(
              semanticLabel: 'Collapse navigation rail',
              onActivate: widget.onToggleCollapse,
              child: Icon(Icons.chevron_left, size: 15, color: t.inkFaint),
            ),
          ] else
            AccessibleAction(
              semanticLabel: 'Expand navigation rail',
              onActivate: widget.onToggleCollapse,
              child: Icon(Icons.chevron_right, size: 15, color: t.inkFaint),
            ),
        ],
      ),
    );
  }

  Widget _footer(BuildContext context) {
    if (widget.inDrawer) return _drawerFooter(context);
    final t = context.fw;
    return Padding(
      padding: const EdgeInsets.all(8),
      child: Row(children: [
        AccessibleAction(
          semanticLabel: 'Toggle theme',
          onActivate: widget.onToggleTheme,
          child: Icon(Icons.contrast, size: 15, color: t.inkFaint),
        ),
        const SizedBox(width: 8),
        AccessibleAction(
          semanticLabel: 'Open recovery center',
          onActivate: widget.onOpenRecovery,
          child: Icon(Icons.restore_rounded, size: 15, color: t.inkFaint),
        ),
        const SizedBox(width: 8),
        if (widget.onOpenAssistant != null) ...[
          AccessibleAction(
            semanticLabel: 'Open assistant',
            onActivate: widget.onOpenAssistant!,
            child: Icon(Icons.assistant_rounded, size: 15, color: t.inkFaint),
          ),
          const SizedBox(width: 8),
        ],
        if (widget.onOpenSessions != null) ...[
          AccessibleAction(
            semanticLabel: 'Open sessions',
            onActivate: widget.onOpenSessions!,
            child: Icon(Icons.history_rounded, size: 15, color: t.inkFaint),
          ),
          const SizedBox(width: 8),
        ],
        if (widget.onOpenConnection != null) ...[
          AccessibleAction(
            semanticLabel: 'Pair a gateway connection',
            onActivate: widget.onOpenConnection!,
            child: Icon(Icons.devices_rounded, size: 15, color: t.inkFaint),
          ),
          const SizedBox(width: 8),
        ],
        AccessibleAction(
          semanticLabel: 'Open appearance settings',
          onActivate: widget.onOpenAppearance,
          child: Icon(Icons.tune, size: 15, color: t.inkFaint),
        ),
      ]),
    );
  }

  Widget _drawerFooter(BuildContext context) {
    final t = context.fw;
    return Column(
      children: [
        Divider(color: t.line, height: 1),
        const SizedBox(height: FwLayout.s2),
        _footerKicker(t, 'TOOLS'),
        if (widget.onOpenAssistant != null)
          _drawerAction(t, Icons.assistant_rounded, 'Assistant',
              widget.onOpenAssistant!,
              semantic: 'Open assistant'),
        if (widget.onOpenSessions != null)
          _drawerAction(t, Icons.history_rounded, 'Sessions',
              widget.onOpenSessions!,
              semantic: 'Open sessions'),
        _drawerAction(t, Icons.restore_rounded, 'Recovery',
            widget.onOpenRecovery,
            semantic: 'Open recovery center'),
        Container(
          height: 1,
          margin: const EdgeInsets.symmetric(
              horizontal: FwLayout.s3, vertical: FwLayout.s1),
          color: t.hairline,
        ),
        _footerKicker(t, 'SETTINGS'),
        _drawerAction(t, Icons.contrast, 'Theme', widget.onToggleTheme,
            semantic: 'Toggle theme'),
        _drawerAction(t, Icons.tune, 'Appearance', widget.onOpenAppearance,
            semantic: 'Open appearance settings'),
        if (widget.onOpenConnection != null)
          _drawerAction(t, Icons.devices_rounded, 'Connection',
              widget.onOpenConnection!,
              semantic: 'Pair a gateway connection'),
        const SizedBox(height: FwLayout.s2),
      ],
    );
  }

  Widget _footerKicker(FwTokens t, String text) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 2),
      child:
          Text(text, style: fwKicker(t, size: 9, color: t.inkFaint)),
    );
  }

  Widget _drawerAction(
      FwTokens t, IconData icon, String label, VoidCallback onTap,
      {String? semantic}) {
    return AccessibleAction(
      semanticLabel: semantic ?? label,
      onActivate: onTap,
      child: ExcludeSemantics(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
          child: Row(children: [
            Icon(icon, size: 17, color: t.inkMuted),
            const SizedBox(width: 10),
            Text(label, style: TextStyle(fontSize: 13, color: t.inkSoft)),
          ]),
        ),
      ),
    );
  }
}
