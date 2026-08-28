// mobile_nav_bar.dart -- the phone's primary navigation.
//
// A phone opens on one clear surface and shows a few first-run destinations in
// a bottom bar, so a new user is not handed the whole thirty-two-item catalog
// behind a drawer. More opens that full catalog; nothing is removed.
//
// The bar mirrors the side rail's grammar: a mono abbr tag, an ink accent for
// the selected item, and verdict-only color. No Material icon set, no colored
// pills, so the phone and the desktop read as one app.
import 'package:flutter/material.dart';

import '../accessibility/accessible_action.dart';
import '../navigation/app_route.dart';
import '../navigation/destination_catalog.dart';
import '../theme/flywheel_theme.dart';

class MobileNavBar extends StatelessWidget {
  final List<DestinationSpec> primaries;
  final DestinationId selected;
  final ValueChanged<DestinationId> onGo;
  final VoidCallback onMore;

  const MobileNavBar({
    super.key,
    required this.primaries,
    required this.selected,
    required this.onGo,
    required this.onMore,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(top: BorderSide(color: t.line)),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 58,
          child: Row(
            children: [
              for (final spec in primaries)
                Expanded(
                  child: _NavItem(
                    label: spec.label,
                    code: spec.abbr,
                    selected: spec.id == selected,
                    onTap: () => onGo(spec.id),
                  ),
                ),
              // More is never the selected state: it opens the full catalog
              // rather than being a destination of its own.
              Expanded(
                child: _NavItem(
                  label: 'More',
                  code: '•••',
                  selected: false,
                  onTap: onMore,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final String label;
  final String code;
  final bool selected;
  final VoidCallback onTap;

  const _NavItem({
    required this.label,
    required this.code,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final ink = selected ? t.ink : t.inkMuted;
    return AccessibleAction(
      semanticLabel: label,
      selected: selected,
      onActivate: onTap,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
        padding: const EdgeInsets.symmetric(vertical: 4),
        decoration: BoxDecoration(
          color: selected ? t.panel : Colors.transparent,
          borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 20,
              height: 2.5,
              decoration: BoxDecoration(
                color: selected ? t.ink : Colors.transparent,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 5),
            Text(code, style: fwKicker(t, size: 9.5, color: ink)),
            const SizedBox(height: 3),
            Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 10.5,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                color: ink,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
