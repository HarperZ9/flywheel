// nav_search_field.dart -- the rail's destination filter. Typing narrows
// every group to matches on stable label text; the field is a semantic
// search box with visible focus and a clear action.
import 'package:flutter/material.dart';

import '../accessibility/accessible_action.dart';
import '../theme/flywheel_theme.dart';

class NavSearchField extends StatelessWidget {
  final ValueChanged<String> onChanged;
  final TextEditingController controller;
  const NavSearchField(
      {super.key, required this.onChanged, required this.controller});

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return ValueListenableBuilder<TextEditingValue>(
      valueListenable: controller,
      builder: (context, value, _) => Padding(
        padding: const EdgeInsets.fromLTRB(
            FwLayout.s2, 0, FwLayout.s2, FwLayout.s2),
        child: TextField(
          controller: controller,
          onChanged: onChanged,
          style: TextStyle(fontSize: 12.5, color: t.ink),
          decoration: InputDecoration(
            isDense: true,
            prefixIcon: Icon(Icons.search_rounded,
                size: 14, color: t.inkFaint),
            suffixIcon: value.text.isEmpty
                ? null
                : AccessibleAction(
                    semanticLabel: 'Clear destination search',
                    onActivate: () => controller.clear(),
                    child: Icon(Icons.close_rounded,
                        size: 13, color: t.inkFaint),
                  ),
            hintText: 'Find a destination',
            hintStyle: TextStyle(fontSize: 12, color: t.inkFaint),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
              borderSide: BorderSide(color: t.line),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
              borderSide: BorderSide(color: t.line),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(FwLayout.radiusSmall),
              borderSide: BorderSide(color: t.inkMuted),
            ),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          ),
        ),
      ),
    );
  }
}
