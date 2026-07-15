// tab_bar.dart — the Code view's open-file tabs: dirty markers in drift,
// the active tab carrying the single hot bar, close per tab, and the
// close-workspace action.

import 'package:flutter/material.dart';

import '../theme/flywheel_theme.dart';
import '../widgets/fw.dart';
import 'editor_pane.dart';

class EditorTabBar extends StatelessWidget {
  final List<OpenFile> open;
  final int active;
  final ValueChanged<int> onSelect;
  final ValueChanged<int> onClose;
  final VoidCallback onCloseWorkspace;
  const EditorTabBar(
      {super.key,
      required this.open,
      required this.active,
      required this.onSelect,
      required this.onClose,
      required this.onCloseWorkspace});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      height: 34,
      decoration: BoxDecoration(
        color: t.ground2,
        border: Border(bottom: BorderSide(color: t.line)),
      ),
      child: Row(
        children: [
          Expanded(
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                for (var i = 0; i < open.length; i++) _tab(t, i),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(right: FwLayout.s2),
            child: MouseRegion(
              cursor: SystemMouseCursors.click,
              child: GestureDetector(
                onTap: onCloseWorkspace,
                child: Text('close workspace',
                    style: fwMono(t, size: 10.5, color: t.inkFaint)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _tab(FwTokens t, int i) {
    final f = open[i];
    final isActive = i == active;
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => onSelect(i),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: FwLayout.s3),
          decoration: BoxDecoration(
            color: isActive ? t.ground : Colors.transparent,
            border: Border(
              right: BorderSide(color: t.hairline),
              top: BorderSide(
                  color: isActive ? t.ink : Colors.transparent, // selection = ink, not a verdict
                  width: 2),
            ),
          ),
          child: Row(
            children: [
              if (f.dirty) ...[
                const VerdictDot('drift', size: 6),
                const SizedBox(width: 5),
              ],
              Text(f.name,
                  style: fwMono(t,
                      size: 11.5,
                      color: isActive ? t.ink : t.inkMuted,
                      weight: isActive ? FontWeight.w600 : FontWeight.w400)),
              const SizedBox(width: 6),
              GestureDetector(
                onTap: () => onClose(i),
                child: Icon(Icons.close, size: 11, color: t.inkFaint),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
