// url_device_sink.dart -- the real device target: open the link a plan produces.
//
// A navigation or music plan is an http or https deep link (maps directions, a
// music search); this launches it in the phone's own app. The internal media and
// timer actions are not links, so they report not-yet-handled rather than
// pretending to open: those need a platform channel (a media session, a local
// notification), which is the next device capability to add. Every result is an
// honest bool the executor records.

import 'package:url_launcher/url_launcher.dart';

import 'assistant_executor.dart';

class UrlLauncherDeviceSink implements DeviceSink {
  UrlLauncherDeviceSink({Future<bool> Function(Uri)? launcher})
      : _launch = launcher ??
            ((uri) => launchUrl(uri, mode: LaunchMode.externalApplication));

  final Future<bool> Function(Uri) _launch;

  @override
  Future<bool> open(String deepLink) async {
    final uri = Uri.tryParse(deepLink);
    if (uri == null) return false;
    if (uri.isScheme('http') || uri.isScheme('https')) {
      try {
        return await _launch(uri);
      } catch (_) {
        return false; // a launch that throws is an honest failure, not a crash
      }
    }
    // media: and timer: are internal actions handled by a platform channel, not a
    // URL launch, so report not-yet-handled rather than pretending to open them.
    return false;
  }
}
