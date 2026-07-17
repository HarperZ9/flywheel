// compare_view.dart — ask two models the same thing, side by side. One prompt,
// two live threads, two pickers. The single most-loved feature we lacked
// (Msty Split Chats, Cherry Studio parallel runs): stop copy-pasting a prompt
// between tabs to see which model answers better.

import 'dart:async';

import 'package:flutter/material.dart';

import '../client/gateway_client.dart';
import '../models/chat.dart';
import '../models/gateway_models.dart';
import '../services/settings.dart';
import '../theme/flywheel_theme.dart';
import '../widgets/chat_composer.dart';
import '../widgets/chat_thread.dart';
import '../widgets/fw.dart';
import '../widgets/model_picker.dart';
import '../widgets/split_pane.dart';

class CompareView extends StatefulWidget {
  final GatewayClient client;
  final bool alive;
  final DesktopSettings settings;
  const CompareView(
      {super.key,
      required this.client,
      required this.alive,
      required this.settings});

  @override
  State<CompareView> createState() => _CompareViewState();
}

class _Side {
  String? model;
  final messages = <ChatMessage>[];
  final scroll = ScrollController();
  StreamSubscription? sub;
  bool streaming = false;
}

class _CompareViewState extends State<CompareView> {
  final _left = _Side();
  final _right = _Side();
  List<EndpointRow> _endpoints = [];

  @override
  void initState() {
    super.initState();
    _loadEndpoints();
  }

  @override
  void didUpdateWidget(CompareView old) {
    super.didUpdateWidget(old);
    if (!old.alive && widget.alive) _loadEndpoints();
  }

  @override
  void dispose() {
    _left.sub?.cancel();
    _right.sub?.cancel();
    _left.scroll.dispose();
    _right.scroll.dispose();
    super.dispose();
  }

  bool get _busy => _left.streaming || _right.streaming;

  Future<void> _loadEndpoints() async {
    if (!widget.alive) return;
    try {
      final rows = await widget.client.endpointRoster();
      if (mounted) {
        setState(() {
          _endpoints = rows;
          _left.model ??= rows.isNotEmpty ? rows.first.name : null;
          _right.model ??=
              rows.length > 1 ? rows[1].name : (rows.isNotEmpty ? rows.first.name : null);
        });
      }
    } catch (_) {/* offline empty-state handles it */}
  }

  void _send(String text) {
    if (_left.model == null && _right.model == null) return;
    setState(() {
      for (final s in [_left, _right]) {
        if (s.model == null) continue;
        s.messages.add(ChatMessage(role: 'user', text: text));
        s.messages.add(ChatMessage(role: 'assistant', streaming: true));
      }
    });
    _run(_left);
    _run(_right);
  }

  void _run(_Side s) {
    if (s.model == null || s.messages.isEmpty) return;
    final assistant = s.messages.last;
    s.streaming = true;
    final wire = s.messages
        .where((m) => !(m.streaming && m.text.isEmpty))
        .map((m) => m.toWire())
        .toList();
    s.sub = widget.client.chatStream(wire, s.model!).listen(
      (e) {
        if (!mounted) return;
        setState(() {
          if (e['type'] == 'delta') assistant.text += e['content'] as String;
          if (e['type'] == 'done') {
            assistant.receipt = e['receipt'] as Map<String, dynamic>?;
          }
        });
        _scroll(s);
      },
      onError: (_) => _finish(s, assistant),
      onDone: () => _finish(s, assistant),
    );
  }

  void _finish(_Side s, ChatMessage assistant) {
    if (!mounted) return;
    setState(() {
      assistant.streaming = false;
      if (assistant.text.isEmpty) {
        assistant.text = 'No reply. This model may be offline; pick another above.';
      }
      s.streaming = false;
    });
  }

  void _stop() {
    for (final s in [_left, _right]) {
      s.sub?.cancel();
      for (final m in s.messages) {
        m.streaming = false;
      }
      s.streaming = false;
    }
    setState(() {});
  }

  void _clear() {
    if (_busy) return;
    setState(() {
      for (final s in [_left, _right]) {
        s.messages.clear();
      }
    });
  }

  void _scroll(_Side s) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (s.scroll.hasClients) {
        s.scroll.jumpTo(s.scroll.position.maxScrollExtent);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.alive) {
      return const FwEmpty('The engine is offline. Compare appears when it runs.',
          command: 'flywheel up');
    }
    final t = context.fw;
    return Column(children: [
      Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s5, vertical: FwLayout.s3),
        decoration:
            BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
        child: Row(children: [
          Text('Compare', style: Theme.of(context).textTheme.titleMedium),
          const Spacer(),
          TextButton.icon(
            onPressed: _busy ? null : _clear,
            icon: const Icon(Icons.restart_alt_rounded, size: 15),
            label: const Text('Clear'),
          ),
        ]),
      ),
      Expanded(
        child: SplitPane(
          axis: Axis.horizontal,
          initialFraction: widget.settings.splitFraction('compare', 0.5),
          minFraction: 0.25,
          maxFraction: 0.75,
          onFraction: (f) => widget.settings.setSplitFraction('compare', f),
          first: _pane(t, _left),
          second: _pane(t, _right),
        ),
      ),
      ChatComposer(
        streaming: _busy,
        onSend: _send,
        onStop: _stop,
        hint: 'Ask both models the same thing…',
        savedPrompts: widget.settings.savedPrompts,
        onSavePrompt: (t) => setState(() => widget.settings.savePrompt(t)),
      ),
    ]);
  }

  Widget _pane(FwTokens t, _Side s) {
    return Column(children: [
      Container(
        padding: const EdgeInsets.symmetric(
            horizontal: FwLayout.s4, vertical: FwLayout.s2),
        decoration:
            BoxDecoration(border: Border(bottom: BorderSide(color: t.hairline))),
        child: Row(children: [
          ModelPickerButton(
            endpoints: _endpoints,
            current: s.model,
            enabled: !_busy,
            onSelect: (v) => setState(() => s.model = v),
          ),
          const Spacer(),
          if (s.streaming)
            SizedBox(
                width: 12,
                height: 12,
                child: CircularProgressIndicator(
                    strokeWidth: 1.6, color: t.inkFaint)),
        ]),
      ),
      Expanded(
        child: s.messages.isEmpty
            ? Center(
                child: Text('Pick a model and send a prompt.',
                    style: TextStyle(color: t.inkFaint, fontSize: 13)))
            : ChatThread(messages: s.messages, controller: s.scroll),
      ),
    ]);
  }
}
