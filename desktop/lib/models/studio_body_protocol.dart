const studioBodyContractVersion = 'flywheel.studio.body/v1';
const studioBodyStatusSchema = 'flywheel.studio.body.status/v1';
const studioBodySnapshotSchema = 'flywheel.studio.body.snapshot/v1';
const studioBodyStepResponseSchema = 'flywheel.studio.body.step-response/v1';
const studioBodySoundActionKind = 'flywheel.studio.sound.compose/v1';
const studioBodySoundTargetPrefix = 'flywheel://studio/sound/';
const studioBodyEngineActionKind = 'flywheel.studio.engine.render-world/v1';
const studioBodyEngineTargetPrefix = 'flywheel://studio/engine/';

enum StudioBodyInstrument { sound, engine }

extension StudioBodyInstrumentText on StudioBodyInstrument {
  String get label => this == StudioBodyInstrument.sound ? 'sound' : 'visual';
}

Map<String, Object?> studioBodyMap(Object? raw) =>
    raw is Map ? Map<String, Object?>.from(raw) : const {};

String studioBodyText(Object? raw) => raw is String &&
        raw.isNotEmpty &&
        raw.length <= 1024 &&
        !RegExp(r'[\x00-\x08\x0b\x0c\x0e-\x1f]').hasMatch(raw)
    ? raw
    : '';

int? studioBodyIntOrNull(Object? raw) => raw is int ? raw : null;

List<String> studioBodyStrings(Object? raw) => raw is List
    ? List<String>.unmodifiable(
        raw.whereType<String>().map(studioBodyText).where((s) => s.isNotEmpty))
    : const [];

List<T> studioBodyRecords<T>(
        Object? raw, T Function(Map<String, Object?>) parse) =>
    raw is List
        ? List<T>.unmodifiable(raw
            .whereType<Map>()
            .map((m) => parse(Map<String, Object?>.from(m))))
        : const [];
