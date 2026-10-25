import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:delipick_app/services/api_service.dart';

void main() {
  test('integrated Android emulator port is the default', () {
    final service = DelipickApiService();
    expect(service.baseUrl, 'http://10.0.2.2:18086');
    service.dispose();
  });
  test('GET query preserves category, text, type and medium tastes', () async {
    final client = MockClient((request) async {
      expect(request.url.path, '/restaurants');
      expect(request.url.queryParameters['category_ids'], '1,2');
      expect(request.url.queryParameters['user_type'], 'gourmet');
      expect(request.url.queryParameters['preference_text'], '안 매운 국물');
      expect(request.url.queryParameters['taste_levels'], contains('salty:1'));
      expect(request.url.queryParameters['taste_levels'], contains('spicy:1'));
      expect(request.url.queryParameters['taste_levels'], isNot(contains('sour')));
      return http.Response(jsonEncode({'mode': 'personalized', 'items': []}), 200);
    });
    final service = DelipickApiService(baseUrl: 'http://example.test', client: client);
    await service.fetchRecommendations(const RecommendationQuery(
      categoryIds: [1, 2], minPrice: 2000, maxPrice: 10000, userType: 'gourmet',
      preferenceText: '안 매운 국물', tasteLevels: {'salty': 1, 'spicy': 1, 'sour': -1},
    ));
    service.dispose();
  });
  test('structured replay errors show their message instead of raw JSON', () async {
    final service = DelipickApiService(client: MockClient((_) async => http.Response(
      jsonEncode({'detail': {'message': 'Replay mode only supports recorded examples.', 'examples': []}}), 422,
    )));
    await expectLater(service.fetchRecommendations(const RecommendationQuery(
      categoryIds: [], minPrice: 0, maxPrice: 10000, userType: '', preferenceText: 'new text',
    )), throwsA(isA<ApiException>().having((e) => e.message, 'message', contains('Replay mode only'))));
    service.dispose();
  });
}
