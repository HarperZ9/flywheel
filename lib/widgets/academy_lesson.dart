// academy_lesson.dart — one lesson of the arc, fully operable: the teach
// text pinned to its source hash, the declared check runnable in place,
// completion bound to a passed comprehension receipt, and the lesson
// renderable as a manim scene when the toolchain is present.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/flywheel_theme.dart';
import 'fw.dart';

typedef RunCheck = Future<(int, String)> Function(String path);
typedef BindCompletion = Future<Map<String, dynamic>> Function(
    String lessonId, String eid);
typedef AnimateLesson = Future<Map<String, dynamic>> Function(
    Map<String, dynamic> lesson);

class AcademyLessonCard extends StatefulWidget {
  final Map<String, dynamic> lesson;
  final int index;
  final RunCheck? onRunCheck;
  final BindCompletion? onBind;
  final AnimateLesson? onAnimate;
  const AcademyLessonCard(
      {super.key,
      required this.lesson,
      required this.index,
      this.onRunCheck,
      this.onBind,
      this.onAnimate});

  @override
  State<AcademyLessonCard> createState() => _AcademyLessonCardState();
}

class _AcademyLessonCardState extends State<AcademyLessonCard> {
  final _eid = TextEditingController();
  (int, String)? _check;
  Map<String, dynamic>? _bound;
  Map<String, dynamic>? _scene;
  bool _checking = false, _binding = false, _animating = false;
  String? _error;

  @override
  void dispose() {
    _eid.dispose();
    super.dispose();
  }

  Map<String, dynamic> get _checkSpec =>
      (widget.lesson['check'] is Map<String, dynamic>)
          ? widget.lesson['check'] as Map<String, dynamic>
          : const {};

  Future<void> _run() async {
    final path = '${_checkSpec['path'] ?? ''}';
    final cb = widget.onRunCheck;
    if (path.isEmpty || cb == null || _checking) return;
    setState(() {
      _checking = true;
      _error = null;
    });
    try {
      final r = await cb(path);
      if (mounted) setState(() => _check = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _bind() async {
    final cb = widget.onBind;
    final eid = _eid.text.trim();
    if (cb == null || eid.isEmpty || _binding) return;
    setState(() {
      _binding = true;
      _error = null;
    });
    try {
      final r = await cb('${widget.lesson['id']}', eid);
      if (mounted) setState(() => _bound = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _binding = false);
    }
  }

  Future<void> _animate() async {
    final cb = widget.onAnimate;
    if (cb == null || _animating) return;
    setState(() {
      _animating = true;
      _error = null;
    });
    try {
      final r = await cb(widget.lesson);
      if (mounted) setState(() => _scene = r);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _animating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = context.fw;
    final l = widget.lesson;
    final prereqs = (l['prereqs'] ?? []) as List;
    final isGet = '${_checkSpec['method'] ?? ''}'.toUpperCase() == 'GET';
    return HairlineCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            VerdictDot(
                (l['present'] ?? false) == true ? 'verified' : 'unverifiable'),
            const SizedBox(width: FwLayout.s2),
            Expanded(
              child: Text(
                  '${widget.index + 1}. ${l['title'] ?? ''}'
                  '${prereqs.isEmpty ? '' : '  <- ${prereqs.join(', ')}'}',
                  style: fwMono(t, size: 12.5).copyWith(color: t.ink)),
            ),
          ]),
          const SizedBox(height: FwLayout.s2),
          Text('${l['teach'] ?? ''}',
              style: TextStyle(fontSize: 13, height: 1.45, color: t.inkSoft)),
          const SizedBox(height: FwLayout.s2),
          Text(
              'check: ${_checkSpec['method'] ?? ''} ${_checkSpec['path'] ?? ''} '
              '-> ${_checkSpec['expect'] ?? ''}',
              style: fwMono(t, size: 11.5).copyWith(color: t.inkMuted)),
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            if (isGet)
              OutlinedButton(
                onPressed:
                    widget.onRunCheck == null || _checking ? null : _run,
                child: Text(_checking ? 'Running…' : 'Run check'),
              )
            else
              Text('this check runs from its own composer',
                  style: fwMono(t, size: 11).copyWith(color: t.inkFaint)),
            const SizedBox(width: FwLayout.s3),
            OutlinedButton(
              onPressed: widget.onAnimate == null || _animating ? null : _animate,
              child: Text(_animating ? 'Composing…' : 'Animate'),
            ),
          ]),
          if (_check != null) ...[
            const SizedBox(height: FwLayout.s2),
            Row(children: [
              VerdictPill(
                  _check!.$1 >= 200 && _check!.$1 < 300
                      ? 'responded ${_check!.$1}'
                      : 'failed ${_check!.$1}',
                  status: _check!.$1 >= 200 && _check!.$1 < 300
                      ? 'verified'
                      : 'drift'),
            ]),
            const SizedBox(height: FwLayout.s2),
            Text(_check!.$2,
                style: fwMono(t, size: 11).copyWith(color: t.inkMuted)),
          ],
          if (_scene != null) ...[
            const SizedBox(height: FwLayout.s3),
            Row(children: [
              VerdictPill(
                  _scene!['renderable'] == true
                      ? 'renderable'
                      : 'manimgl absent',
                  status: _scene!['renderable'] == true
                      ? 'verified'
                      : 'unverifiable'),
              const SizedBox(width: FwLayout.s2),
              Expanded(
                child: Text('${_scene!['scene'] ?? ''}',
                    style: fwMono(t, size: 11.5)),
              ),
              IconButton(
                tooltip: 'Copy scene source',
                icon: const Icon(Icons.copy, size: 14),
                onPressed: () => Clipboard.setData(
                    ClipboardData(text: '${_scene!['source'] ?? ''}')),
              ),
            ]),
            Container(
              width: double.infinity,
              constraints: const BoxConstraints(maxHeight: 180),
              padding: const EdgeInsets.all(FwLayout.s3),
              decoration: BoxDecoration(
                  border: Border.all(color: t.hairline),
                  borderRadius: BorderRadius.circular(4)),
              child: SingleChildScrollView(
                child: SelectableText('${_scene!['source'] ?? ''}',
                    style: fwMono(t, size: 11).copyWith(color: t.inkSoft)),
              ),
            ),
          ],
          const SizedBox(height: FwLayout.s3),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _eid,
                style: const TextStyle(fontSize: 12.5),
                decoration: const InputDecoration(
                    hintText:
                        'comprehension receipt eid (bank one with a teach-back)'),
              ),
            ),
            const SizedBox(width: FwLayout.s3),
            OutlinedButton(
              onPressed: widget.onBind == null || _binding ? null : _bind,
              child: Text(_binding ? 'Binding…' : 'Bind completion'),
            ),
          ]),
          if (_bound != null) ...[
            const SizedBox(height: FwLayout.s2),
            if (_bound!['bound'] == true)
              Row(children: [
                const VerdictPill('completion bound', status: 'verified'),
                const SizedBox(width: FwLayout.s2),
                Expanded(
                    child: HashText('chain', '${_bound!['chain_hash'] ?? ''}',
                        keep: 16)),
              ])
            else
              HonestNull('${_bound!['reason'] ?? 'not bound'}'),
          ],
          if (_error != null) ...[
            const SizedBox(height: FwLayout.s2),
            HonestNull('Failed: $_error'),
          ],
          if ('${l['source_sha256'] ?? ''}'.isNotEmpty)
            HashText('source', '${l['source_sha256']}', keep: 16),
        ],
      ),
    );
  }
}
