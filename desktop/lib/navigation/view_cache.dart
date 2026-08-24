// view_cache.dart -- per-destination state retention.
//
// Each destination's subtree lives inside a stable PageStorage bucket, so
// scroll positions and PageStorage-backed state survive switching away
// and back. Widgets are not retained: a destination rebuilds on return
// and re-reads its server truth; only its own view state persists.
import 'package:flutter/widgets.dart';

import '../navigation/app_route.dart';

class ViewCache {
  final PageStorageBucket _bucket = PageStorageBucket();

  Key keyFor(AppLocation location) =>
      Key('dest-${location.routeId.name}');

  Widget viewFor(AppLocation location, WidgetBuilder build) =>
      PageStorage(
        bucket: _bucket,
        child: KeyedSubtree(
            key: keyFor(location), child: Builder(builder: build)),
      );
}
