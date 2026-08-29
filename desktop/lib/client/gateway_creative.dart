part of 'gateway_client.dart';

extension GatewayCreative on GatewayClient {
  /// POST /api/typeface — mint a parametric face; outlines + receipt back.
  Future<Map<String, dynamic>> typefaceMint(
      Map<String, dynamic> params, int seed) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/typeface'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'params': params,
        'seed': seed,
        'ttf': true,
        'family': 'Zentropy Mint $seed',
      }),
    );
    return _decode(r);
  }

  /// POST /api/typeface/publish — file a minted face in the witnessed gallery.
  Future<Map<String, dynamic>> typefacePublish(
      Map<String, dynamic> params, int seed,
      {String family = ''}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/typeface/publish'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'params': params,
        'seed': seed,
        if (family.isNotEmpty) 'family': family,
      }),
    );
    return _decode(r);
  }

  /// GET /api/typeface/gallery — the marketplace listing (metadata only).
  Future<Map<String, dynamic>> typefaceGallery({int limit = 60}) =>
      getJson('/api/typeface/gallery?limit=$limit');

  /// GET /api/typeface/face — one published face with its .ttf bytes.
  Future<Map<String, dynamic>> typefaceFace(String eid) =>
      getJson('/api/typeface/face?eid=$eid');

  /// POST /api/typeface/variable — the family's weights as ONE variable font
  /// with a wght axis; the response carries the .ttf and a receipt.
  Future<Map<String, dynamic>> typefaceVariable(
      Map<String, dynamic> params, int seed) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/typeface/variable'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'params': params,
        'seed': seed,
        'family': 'Zentropy Mint $seed',
      }),
    );
    return _decode(r);
  }

  /// POST /api/studio/poster — plate + minted face + copy under one receipt.
  Future<Map<String, dynamic>> studioPoster(String title,
      {String subtitle = '',
      String format = 'poster',
      int seed = 58,
      String ground = 'dark',
      bool accent = true,
      Map<String, dynamic>? faceParams}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/poster'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'title': title,
        'subtitle': subtitle,
        'format': format,
        'seed': seed,
        'ground': ground,
        'accent': accent,
        if (faceParams != null) 'face_params': faceParams,
      }),
    );
    return _decode(r);
  }

  /// POST /api/telos/kernel — run a bridged telos creative kernel; the
  /// answer (points, bounds, receipt hashes) is the kernel's own.
  Future<Map<String, dynamic>> telosKernel(
      String kernel, Map<String, dynamic> args) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/telos/kernel'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'kernel': kernel, 'args': args}),
    );
    return _decode(r);
  }

  /// POST /api/telos/raster — dither or pixel-sort over a plate or PNG;
  /// the receipt carries the kernel's own hashes.
  Future<Map<String, dynamic>> telosRaster(String kernel,
      {Map<String, dynamic>? source, Map<String, dynamic>? args}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/telos/raster'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'kernel': kernel,
        if (source != null) 'source': source,
        if (args != null) 'args': args,
      }),
    );
    return _decode(r);
  }

  /// POST /api/studio/graph — a branching creative DAG; every node's chain
  /// folds its inputs' chains, so the graph id witnesses everything.
  Future<Map<String, dynamic>> studioGraph(List<Map<String, dynamic>> nodes,
      List<Map<String, dynamic>> edges) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/graph'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'nodes': nodes, 'edges': edges}),
    );
    return _decode(r);
  }

  /// POST /api/studio/pipeline — ordered creative stages, one chained
  /// receipt; the pipeline id witnesses the whole line in order.
  Future<Map<String, dynamic>> studioPipeline(
      List<Map<String, dynamic>> stages) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/pipeline'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'stages': stages}),
    );
    return _decode(r);
  }

  /// POST /api/studio/brandkit — one seed + a name -> a whole identity.
  Future<Map<String, dynamic>> brandKit(String name,
      {String tagline = '',
      int seed = 58,
      Map<String, dynamic>? faceParams}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/brandkit'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'name': name,
        'tagline': tagline,
        'seed': seed,
        if (faceParams != null) 'face_params': faceParams,
      }),
    );
    return _decode(r);
  }

  /// POST /api/studio/sound — the seeded chime study; the score is the receipt.
  Future<Map<String, dynamic>> studioSound(
      {int seed = 58, double duration = 24, double root = 220}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/studio/sound'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'seed': seed, 'duration': duration, 'root': root}),
    );
    return _decode(r);
  }

  /// POST /api/forge — turn a plain goal into a structured prompt with gates.
  /// [authorizedBody] is the grant-approved operation body, sent verbatim.
  Future<Map<String, dynamic>> forge(String goal,
      {String? context,
      List<String>? examples,
      Map<String, dynamic>? authorizedBody}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/forge'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(authorizedBody ?? {
        'goal': goal,
        if (context != null) 'context': context,
        if (examples != null) 'examples': examples,
      }),
    );
    return _decode(r);
  }

  /// POST /api/forge/recheck — has an arm drifted since the forge sealed it?
  Future<Map<String, dynamic>> forgeRecheck(String prpId,
      {Map<String, dynamic>? authorizedBody}) async {
    final r = await _http.post(
      Uri.parse('$baseUrl/api/forge/recheck'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(authorizedBody ?? {'prp_id': prpId}),
    );
    return _decode(r);
  }
}
