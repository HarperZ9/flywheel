// chat_composer.dart — the message input. Enter sends, Shift+Enter makes a
// newline; a Stop button replaces Send while a turn streams so a run is always
// cancellable. Warm and roomy: the composer is where the user lives.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/flywheel_theme.dart';

class ChatComposer extends StatefulWidget {
  final bool streaming;
  final ValueChanged<String> onSend;
  final VoidCallback onStop;
  final String hint;
  const ChatComposer({
    super.key,
    required this.streaming,
    required this.onSend,
    required this.onStop,
    this.hint = 'Message the agent…',
  });

  @override
  State<ChatComposer> createState() => _ChatComposerState();
}

class _ChatComposerState extends State<ChatComposer> {
  final _controller = TextEditingController();
  final _focus = FocusNode();
  bool _hasText = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(() {
      final has = _controller.text.trim().isNotEmpty;
      if (has != _hasText) setState(() => _hasText = has);
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _send() {
    final text = _controller.text.trim();
    if (text.isEmpty || widget.streaming) return;
    widget.onSend(text);
    _controller.clear();
    _focus.requestFocus();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is KeyDownEvent &&
        event.logicalKey == LogicalKeyboardKey.enter &&
        !HardwareKeyboard.instance.isShiftPressed) {
      _send();
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    return Container(
      padding: const EdgeInsets.fromLTRB(
          FwLayout.s5, FwLayout.s3, FwLayout.s5, FwLayout.s4),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: t.hairline)),
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: Container(
          decoration: BoxDecoration(
            color: t.panel,
            borderRadius: BorderRadius.circular(FwLayout.radius),
            border: Border.all(color: t.line),
          ),
          padding: const EdgeInsets.fromLTRB(FwLayout.s4, 4, 6, 6),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Focus(
                  onKeyEvent: _onKey,
                  child: TextField(
                    controller: _controller,
                    focusNode: _focus,
                    minLines: 1,
                    maxLines: 8,
                    textInputAction: TextInputAction.newline,
                    style: TextStyle(fontSize: 14, height: 1.45, color: t.ink),
                    decoration: InputDecoration(
                      isDense: true,
                      border: InputBorder.none,
                      hintText: widget.hint,
                      hintStyle: TextStyle(color: t.inkFaint, fontSize: 14),
                      contentPadding: const EdgeInsets.symmetric(vertical: 10),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: FwLayout.s2),
              _actionButton(t),
            ],
          ),
        ),
      ),
    );
  }

  Widget _actionButton(FwTokens t) {
    if (widget.streaming) {
      return IconButton.filled(
        onPressed: widget.onStop,
        icon: const Icon(Icons.stop_rounded, size: 18),
        style: IconButton.styleFrom(
            backgroundColor: t.drift, foregroundColor: t.ground),
        tooltip: 'Stop',
      );
    }
    return IconButton.filled(
      onPressed: _hasText ? _send : null,
      icon: const Icon(Icons.arrow_upward_rounded, size: 18),
      style: IconButton.styleFrom(
        backgroundColor: _hasText ? t.ink : t.ground2,
        foregroundColor: _hasText ? t.ground : t.inkFaint,
      ),
      tooltip: 'Send  (Enter)',
    );
  }
}
