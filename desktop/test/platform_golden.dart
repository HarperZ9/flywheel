import 'dart:io';

/// Font rasterization differs by host even with pinned SDK and bundled fonts.
/// Windows keeps the original paths; other hosts require reviewed baselines.
/// Missing baselines still fail through Flutter's exact pixel comparator.
String platformGolden(String name) => Platform.isWindows
    ? 'goldens/$name.png'
    : 'goldens/${Platform.operatingSystem}/$name.png';
