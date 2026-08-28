// chat_composer.dart — the message input. Enter sends, Shift+Enter makes a
// newline. Stop appears only when a server-owned operation supplies control.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/chat.dart';
import '../theme/flywheel_theme.dart';

/// Curated starting points so the composer is never a cold blank box.
/// Public so ChatWelcome can render tappable chips from the same list.
const chatStarters = <Map<String, String>>[
  {
    'title': 'Explain this code',
    'text': 'Explain what this code does, step by step:\n\n'
  },
  {
    'title': 'Write tests',
    'text': 'Write thorough tests with meaningful assertions for:\n\n'
  },
  {
    'title': 'Find the bug',
    'text': 'Find and fix the bug in this code, and explain the cause:\n\n'
  },
  {
    'title': 'Refactor for clarity',
    'text': 'Refactor this for readability without changing behavior:\n\n'
  },
  {'title': 'Summarize', 'text': 'Summarize the key points concisely:\n\n'},
  {
    'title': 'Plan it out',
    'text': 'Break this task into a clear, ordered plan before any code:\n\n'
  },
];

class ChatComposer extends StatefulWidget {
  final bool streaming;
  final SubmitPrompt onSend;
  final String initialText;
  final ValueChanged<String> onDraftChanged;
  final VoidCallback? onStop;
  final bool canStop;
  final String hint;

  /// The user's saved prompts ([{title, text}]) and a callback to save the
  /// current composer text to the shelf. When null, only starters are offered.
  final List<Map<String, String>> savedPrompts;
  final ValueChanged<String>? onSavePrompt;
  const ChatComposer({
    super.key,
    required this.streaming,
    required this.onSend,
    required this.onDraftChanged,
    this.onStop,
    this.canStop = false,
    this.initialText = '',
    this.hint = 'Message the agent…',
    this.savedPrompts = const [],
    this.onSavePrompt,
  });

  @override
  State<ChatComposer> createState() => _ChatComposerState();
}

class _ChatComposerState extends State<ChatComposer> {
  final _controller = TextEditingController();
  final _focus = FocusNode();
  bool _hasText = false;
  bool _pending = false;
  bool _suppressDraft = false;

  @override
  void initState() {
    super.initState();
    _controller.text = widget.initialText;
    _hasText = _controller.text.trim().isNotEmpty;
    _controller.addListener(_changed);
  }

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _changed() {
    final hasText = _controller.text.trim().isNotEmpty;
    if (hasText != _hasText && mounted) setState(() => _hasText = hasText);
    if (!_suppressDraft) widget.onDraftChanged(_controller.text);
  }

  Future<void> _send() async {
    final submitted = _controller.text;
    if (submitted.trim().isEmpty || widget.streaming || _pending) return;
    setState(() => _pending = true);
    PromptDisposition disposition;
    try {
      disposition = await widget.onSend(submitted);
    } catch (_) {
      disposition = PromptDisposition.retained;
    }
    if (!mounted) return;
    if (disposition == PromptDisposition.accepted &&
        _controller.text == submitted) {
      _suppressDraft = true;
      _controller.clear();
      _suppressDraft = false;
    }
    setState(() => _pending = false);
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
              _shelfButton(t),
              const SizedBox(width: 2),
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

  Widget _shelfButton(FwTokens t) {
    const saveValue = '\u0000save';
    return PopupMenuButton<String>(
      tooltip: 'Prompts',
      icon: Icon(Icons.bookmark_border_rounded, size: 18, color: t.inkFaint),
      padding: EdgeInsets.zero,
      constraints: const BoxConstraints(minWidth: 260, maxWidth: 340),
      position: PopupMenuPosition.over,
      onSelected: (v) {
        if (v == saveValue) {
          widget.onSavePrompt?.call(_controller.text);
        } else {
          _controller.text = v;
          _controller.selection = TextSelection.collapsed(offset: v.length);
          _focus.requestFocus();
        }
      },
      itemBuilder: (context) => [
        _menuHeader(t, 'Starters'),
        for (final p in chatStarters)
          PopupMenuItem(
              value: p['text'], height: 38, child: _menuRow(t, p['title']!)),
        if (widget.savedPrompts.isNotEmpty) ...[
          const PopupMenuDivider(),
          _menuHeader(t, 'Saved'),
          for (final p in widget.savedPrompts)
            PopupMenuItem(
                value: p['text'], height: 38, child: _menuRow(t, p['title']!)),
        ],
        if (widget.onSavePrompt != null) ...[
          const PopupMenuDivider(),
          PopupMenuItem(
            value: saveValue,
            enabled: _hasText,
            height: 38,
            child: Row(children: [
              Icon(Icons.add_rounded, size: 15, color: t.inkMuted),
              const SizedBox(width: FwLayout.s2),
              Text('Save current prompt',
                  style: TextStyle(fontSize: 13, color: t.inkMuted)),
            ]),
          ),
        ],
      ],
    );
  }

  PopupMenuItem<String> _menuHeader(FwTokens t, String label) => PopupMenuItem(
        enabled: false,
        height: 26,
        child: Text(label.toUpperCase(),
            style: fwMono(t, size: 9.5, color: t.inkFaint)),
      );

  Widget _menuRow(FwTokens t, String title) => Text(title,
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(fontSize: 13, color: t.ink));

  Widget _actionButton(FwTokens t) {
    if (widget.streaming) {
      if (!widget.canStop || widget.onStop == null) {
        return SizedBox(
            width: 40,
            height: 40,
            child: Icon(Icons.more_horiz_rounded, color: t.inkFaint));
      }
      return IconButton.filled(
        onPressed: widget.onStop,
        icon: const Icon(Icons.stop_rounded, size: 18),
        style: IconButton.styleFrom(
            backgroundColor: t.drift, foregroundColor: t.ground),
        tooltip: 'Stop',
      );
    }
    return IconButton.filled(
      onPressed: _hasText && !_pending ? _send : null,
      icon: const Icon(Icons.arrow_upward_rounded, size: 18),
      style: IconButton.styleFrom(
        backgroundColor: _hasText ? t.ink : t.ground2,
        foregroundColor: _hasText ? t.ground : t.inkFaint,
      ),
      tooltip: 'Send  (Enter)',
    );
  }
}
