// action_registry.dart -- the audited inventory of shell interactions.
//
// Every interactive surface registers a stable semantic label, its
// keyboard path, and its enabled reason. The accessibility tests walk
// this registry: an entry without a keyboard path is a defect, not a
// default. Pointer behavior is preserved alongside; the registry names
// the keyboard contract, it does not replace the pointer one.
import 'package:flutter/services.dart';

class RegisteredAction {
  final String semanticLabel;
  final LogicalKeyboardKey? primaryKey;
  final String surface;
  final String enabledReason;
  const RegisteredAction({
    required this.semanticLabel,
    required this.surface,
    this.primaryKey,
    this.enabledReason = 'available',
  });
}

/// The shell's critical keyboard-reachable actions. Surfaces audited in
/// Phase 3/T3: rail items, resizer, split divider, graph canvas, tabs,
/// file tree, chat sidebar delete, status bar, palette, composer.
const actionRegistry = <RegisteredAction>[
  RegisteredAction(
      semanticLabel: 'Open destination',
      surface: 'rail items',
      primaryKey: LogicalKeyboardKey.enter),
  RegisteredAction(
      semanticLabel: 'Resize navigation rail',
      surface: 'rail resizer',
      primaryKey: LogicalKeyboardKey.arrowRight,
      enabledReason: 'arrow keys nudge, Home/End jump to bounds'),
  RegisteredAction(
      semanticLabel: 'Resize panes',
      surface: 'split divider',
      primaryKey: LogicalKeyboardKey.arrowRight,
      enabledReason: 'arrow keys nudge along the divider axis'),
  RegisteredAction(
      semanticLabel: 'Knowledge graph canvas',
      surface: 'graph canvas',
      primaryKey: LogicalKeyboardKey.arrowRight,
      enabledReason: 'arrow keys cycle nodes, Escape clears'),
  RegisteredAction(
      semanticLabel: 'Open file',
      surface: 'editor tab bar',
      primaryKey: LogicalKeyboardKey.enter),
  RegisteredAction(
      semanticLabel: 'Open file from tree',
      surface: 'file tree',
      primaryKey: LogicalKeyboardKey.enter),
  RegisteredAction(
      semanticLabel: 'Delete conversation',
      surface: 'chat sidebar',
      primaryKey: LogicalKeyboardKey.enter),
  RegisteredAction(
      semanticLabel: 'Start engine',
      surface: 'status bar',
      primaryKey: LogicalKeyboardKey.enter),
  RegisteredAction(
      semanticLabel: 'Command palette',
      surface: 'shell',
      primaryKey: LogicalKeyboardKey.keyK,
      enabledReason: 'Ctrl+K opens; arrows move; Enter opens; Escape closes'),
  RegisteredAction(
      semanticLabel: 'Send message',
      surface: 'chat composer',
      primaryKey: LogicalKeyboardKey.enter,
      enabledReason: 'Enter sends; Shift+Enter makes a newline'),
];
