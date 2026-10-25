import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:delipick_app/food_list.dart';
import 'package:delipick_app/models/restaurant.dart';
import 'package:delipick_app/services/api_service.dart';
import 'package:delipick_app/taste_preference.dart';

RecommendationData result(String name, {String mode = 'personalized'}) => RecommendationData(
  mode: mode, userType: null, preferenceText: '',
  items: [RestaurantItem.fromJson({'id': 1, 'name': name, 'main_menu': '메뉴'})],
);

class FakeApi extends DelipickApiService {
  final List<Completer<RecommendationData>> pending = [];
  @override
  Future<List<CategoryItem>> fetchCategories() async => [];
  @override
  Future<RecommendationData> fetchRecommendations(RecommendationQuery query) {
    final completer = Completer<RecommendationData>();
    pending.add(completer);
    return completer.future;
  }
}

void main() {
  testWidgets('loads recommendations without real HTTP and labels personalization', (tester) async {
    final api = FakeApi();
    await tester.pumpWidget(MaterialApp(home: FoodListScreen(apiService: api)));
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    api.pending.single.complete(result('테스트 음식점'));
    await tester.pumpAndSettle();
    expect(find.text('테스트 음식점'), findsOneWidget);
    expect(find.text('취향 반영 추천'), findsOneWidget);
    expect(find.text('기본 정렬: 배달 빠른 순'), findsNothing);
  });

  testWidgets('a stale recommendation response cannot replace the latest one', (tester) async {
    final api = FakeApi();
    await tester.pumpWidget(MaterialApp(home: FoodListScreen(apiService: api)));
    await tester.tap(find.byIcon(Icons.refresh));
    await tester.pump();
    expect(api.pending, hasLength(2));
    api.pending[1].complete(result('최신 음식점'));
    await tester.pumpAndSettle();
    expect(find.text('최신 음식점'), findsOneWidget);
    api.pending[0].complete(result('이전 음식점'));
    await tester.pumpAndSettle();
    expect(find.text('최신 음식점'), findsOneWidget);
    expect(find.text('이전 음식점'), findsNothing);
  });

  testWidgets('all five medium taste choices survive opening and submitting', (tester) async {
    final middle = {for (final key in ['salty', 'sweet', 'sour', 'spicy', 'umami']) key: 1};
    Map<dynamic, dynamic>? submitted;
    await tester.pumpWidget(MaterialApp(home: Builder(builder: (context) {
      return Scaffold(body: TextButton(onPressed: () async {
        submitted = await Navigator.of(context).push<Map<dynamic, dynamic>>(
          MaterialPageRoute(builder: (_) => TastePreferenceScreen(
            initialUserType: '', initialPreferenceText: '', initialTasteLevels: middle,
          )),
        );
      }, child: const Text('설정 열기')));
    })));
    await tester.tap(find.text('설정 열기'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('이 취향으로 추천받기'));
    await tester.pumpAndSettle();
    expect(submitted?['tasteLevels'], middle);
  });
}
