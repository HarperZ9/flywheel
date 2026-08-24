// accessible_action.dart -- the shared focusable, keyboard-activatable
// action primitive. Every pointer-only GestureDetector in the shell goes
// through this: a semantic button role, a visible focus ring, and Enter
// or Space activation, so no control is reachable only by mouse.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class AccessibleAction extends StatefulWidget {
  /// What the control is, read by screen readers and required on every
  /// instance: an unlabeled action is a defect, not a default.
  final String semanticLabel;
  final VoidCallback? onActivate;
  final Widget child;
  final String? tooltip;
  final bool selected;

  /// Injectable for tests (and for callers that own focus order); when
  /// null the detector creates its own node.
  final FocusNode? focusNode;

  const AccessibleAction({
    super.key,
    required this.semanticLabel,
    required this.child,
    this.onActivate,
    this.tooltip,
    this.selected = false,
    this.focusNode,
  });

  @override
  State<AccessibleAction> createState() => _AccessibleActionState();
}

class _AccessibleActionState extends State<AccessibleAction> {
  bool _focused = false;

  @override
  Widget build(BuildContext context) {
    Widget body = Shortcuts(
      shortcuts: const {
        SingleActivator(LogicalKeyboardKey.enter): ActivateIntent(),
        SingleActivator(LogicalKeyboardKey.space): ActivateIntent(),
      },
      child: Actions(
        actions: {
          ActivateIntent: CallbackAction<ActivateIntent>(
              onInvoke: (_) {
            widget.onActivate?.call();
            return null;
          }),
        },
        child: FocusableActionDetector(
          mouseCursor: SystemMouseCursors.click,
          focusNode: widget.focusNode,
          onShowFocusHighlight: (value) => setState(() => _focused = value),
          child: GestureDetector(
            onTap: widget.onActivate,
            behavior: HitTestBehavior.opaque,
            child: DecoratedBox(
              decoration: BoxDecoration(
                border: _focused
                    ? Border.all(
                        color: Theme.of(context).colorScheme.primary,
                        width: 2,
                      )
                    : null,
                borderRadius: BorderRadius.circular(6),
              ),
              child: widget.child,
            ),
          ),
        ),
      ),
    );
    if (widget.tooltip != null) {
      body = Tooltip(message: widget.tooltip!, child: body);
    }
    return Semantics(
      button: true,
      selected: widget.selected,
      label: widget.semanticLabel,
      child: body,
    );
  }
}
