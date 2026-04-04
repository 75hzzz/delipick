import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/restaurant.dart';

class RecommendationQuery {
  // 필터/정렬 요청값
  final List<int> categoryIds;
  final int minPrice;
  final int maxPrice;
  final String spicyLevel;
  final bool weatherFilter;
  final String sort;
  final int limit;

  const RecommendationQuery({
    required this.categoryIds,
    required this.minPrice,
    required this.maxPrice,
    required this.spicyLevel,
    required this.weatherFilter,
    this.sort = 'delivery',
    this.limit = 30,
  });

  Map<String, dynamic> toJson() {
    // POST 호환용 직렬화
    return {
      'category_ids': categoryIds,
      'min_price': minPrice,
      'max_price': maxPrice,
      'spicy_level': spicyLevel,
      'weather_filter': weatherFilter,
      'sort': sort,
      'limit': limit,
    };
  }
}

class ApiException implements Exception {
  final String message;

  const ApiException(this.message);

  @override
  String toString() => message;
}

class DelipickApiService {
  static const String _defaultBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );
  static const Duration _requestTimeout = Duration(seconds: 12);

  final String baseUrl;
  final http.Client _client;

  DelipickApiService({
    String? baseUrl,
    http.Client? client,
  })  : baseUrl = (baseUrl ?? _defaultBaseUrl).replaceAll(RegExp(r'/+$'), ''),
        _client = client ?? http.Client();

  Future<List<CategoryItem>> fetchCategories() async {
    // 카테고리 목록 조회
    final uri = Uri.parse('$baseUrl/categories');
    final response = await _client.get(uri).timeout(_requestTimeout);

    if (response.statusCode != 200) {
      throw ApiException('카테고리 조회 실패 (${response.statusCode})');
    }

    final body = utf8.decode(response.bodyBytes);
    final dynamic data = jsonDecode(body);

    if (data is! List) {
      throw const ApiException('카테고리 응답 형식이 올바르지 않습니다.');
    }

    final imageMap = <int, String>{
      1: 'assets/korean_food.png',
      2: 'assets/chinese_food.png',
      3: 'assets/japanese_food.png',
      4: 'assets/asian.png',
      5: 'assets/fast_food.png',
      6: 'assets/western_food.png',
      7: 'assets/cafe.png',
    };
    final nameFallbackMap = <int, String>{
      1: '한식',
      2: '중식',
      3: '일식',
      4: '아시안',
      5: '패스트푸드',
      6: '양식',
      7: '카페',
    };

    return data
        .whereType<Map<String, dynamic>>()
        .map((item) {
          final id = (item['category_id'] as num?)?.toInt() ?? -1;
          final rawName = (item['category_name'] as String? ?? '').trim();
          final safeName = rawName.isEmpty || rawName.contains('?')
              ? (nameFallbackMap[id] ?? rawName)
              : rawName;

          return CategoryItem(
            id: id,
            name: safeName,
            imageAsset: imageMap[id] ?? 'assets/icon.png',
          );
        })
        .toList();
  }

  Future<RecommendationData> fetchRecommendations(RecommendationQuery query) async {
    // 가격 범위 보정
    final adjustedMin = query.minPrice < 0 ? 0 : query.minPrice;
    final adjustedMax = query.maxPrice < adjustedMin ? adjustedMin : query.maxPrice;
    // 추천 목록 조회(GET)
    final uri = _buildRestaurantsUri(
        RecommendationQuery(
          categoryIds: query.categoryIds,
          minPrice: adjustedMin,
          maxPrice: adjustedMax,
          spicyLevel: query.spicyLevel,
          weatherFilter: query.weatherFilter,
          sort: query.sort,
          limit: query.limit,
        ),
    );

    final response = await _client.get(uri).timeout(_requestTimeout);

    if (response.statusCode != 200) {
      final body = utf8.decode(response.bodyBytes);
      throw ApiException('추천 조회 실패 (${response.statusCode}): ${_extractErrorDetail(body)}');
    }

    final body = utf8.decode(response.bodyBytes);
    final dynamic data = jsonDecode(body);

    if (data is! Map<String, dynamic>) {
      throw const ApiException('추천 응답 형식이 올바르지 않습니다.');
    }

    return RecommendationData.fromJson(data);
  }

  Uri _buildRestaurantsUri(RecommendationQuery query) {
    // 백엔드 Query 파라미터 매핑
    final queryParams = <String, String>{
      'min_price': query.minPrice.toString(),
      'max_price': query.maxPrice.toString(),
      'weather_filter': query.weatherFilter.toString(),
      'sort': query.sort,
      'limit': query.limit.toString(),
    };

    if (query.categoryIds.isNotEmpty) {
      // 다중 카테고리 직렬화
      queryParams['category_ids'] = query.categoryIds.join(',');
    }
    if (query.spicyLevel.trim().isNotEmpty) {
      // 맵기 필터 직렬화
      queryParams['spicy_level'] = query.spicyLevel.trim();
    }

    return Uri.parse('$baseUrl/restaurants').replace(queryParameters: queryParams);
  }

  String _extractErrorDetail(String responseBody) {
    // FastAPI detail 필드 우선 추출
    try {
      final dynamic decoded = jsonDecode(responseBody);
      if (decoded is Map<String, dynamic>) {
        final detail = decoded['detail'];
        if (detail is String && detail.trim().isNotEmpty) {
          return detail;
        }
      }
    } catch (_) {
      // JSON 파싱 실패 시 원문 반환
    }
    return responseBody;
  }

  void dispose() {
    _client.close();
  }
}
