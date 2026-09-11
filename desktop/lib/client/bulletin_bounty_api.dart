import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/bulletin_bounty_models.dart';

const bulletinBountyDefaultBaseUrl = 'https://bulletin.zaindharper.workers.dev';

abstract interface class BulletinBountyApi {
  Future<BulletinBountyList> listBounties({
    String? room,
    String? requester,
    String? status,
    String? before,
    int limit = 20,
  });
  Future<BulletinBountyDetail> readBounty(String id);
  Future<BulletinBountyTerms> readTerms(String bountyId, int version);
}

final class HttpBulletinBountyApi implements BulletinBountyApi {
  final String baseUrl;
  final http.Client _http;

  HttpBulletinBountyApi({
    this.baseUrl = bulletinBountyDefaultBaseUrl,
    http.Client? httpClient,
  }) : _http = httpClient ?? http.Client();

  @override
  Future<BulletinBountyList> listBounties({
    String? room,
    String? requester,
    String? status,
    String? before,
    int limit = 20,
  }) async =>
      BulletinBountyList.fromJson(await _get('/v1/bounties', {
        if (room != null && room.isNotEmpty) 'room': room,
        if (requester != null && requester.isNotEmpty) 'requester': requester,
        if (status != null && status.isNotEmpty) 'status': status,
        if (before != null && before.isNotEmpty) 'before': before,
        if (limit != 20) 'limit': limit.clamp(1, 100).toString(),
      }));

  @override
  Future<BulletinBountyDetail> readBounty(String id) async =>
      BulletinBountyDetail.fromJson(
          await _get('/v1/bounties/${Uri.encodeComponent(id)}'));

  @override
  Future<BulletinBountyTerms> readTerms(String bountyId, int version) async {
    final body = await _get(
        '/v1/bounties/${Uri.encodeComponent(bountyId)}/terms/$version');
    final terms = body['terms'];
    return BulletinBountyTerms.fromJson(
        terms is Map ? Map<String, Object?>.from(terms) : body);
  }

  Future<Map<String, Object?>> _get(String path,
      [Map<String, String> query = const {}]) async {
    final root = baseUrl.endsWith('/')
        ? baseUrl.substring(0, baseUrl.length - 1)
        : baseUrl;
    final uri = Uri.parse('$root$path')
        .replace(queryParameters: query.isEmpty ? null : query);
    final response =
        await _http.get(uri, headers: {'accept': 'application/json'});
    if (response.statusCode != 200) {
      throw FormatException('$path answered ${response.statusCode}');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) {
      throw FormatException('$path did not return an object');
    }
    return Map<String, Object?>.from(decoded);
  }
}
