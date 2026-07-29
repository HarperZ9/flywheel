// version.dart — the app's release identity, surfaced in the UI.
//
// One constant, no plugin. The truth lives in pubspec.yaml; a drift gate
// (test/version_truth_test.dart) fails the suite the moment the two
// disagree, so this can never silently lie about what is running.

const String appVersion = '0.2.1';
const String appPublisher = 'ZentropyLabs';
const String appReleases = 'github.com/HarperZ9/flywheel-desktop/releases';
