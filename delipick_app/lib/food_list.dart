import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'food_filter.dart';
import 'food_list_category.dart';
import 'food_list_price.dart';
import 'models/restaurant.dart';
import 'services/api_service.dart';

class FoodListScreen extends StatefulWidget {
  const FoodListScreen({super.key});

  @override
  State<FoodListScreen> createState() => _FoodListScreenState();
}

class _FoodListScreenState extends State<FoodListScreen> {
  // 가격 필터 기본값
  static const RangeValues _defaultPriceRange = RangeValues(2000, 100000);
  static const Color _delipickBlue = Color(0xFF64B5F6);

  // API 클라이언트
  final DelipickApiService _apiService = DelipickApiService();

  // 사용자 선택 상태
  List<int> selectedCategories = [];
  RangeValues selectedPriceRange = _defaultPriceRange;
  String currentSpiciness = '';
  bool currentWeatherFilter = false;

  // 화면 렌더링 상태
  bool isLoading = true;
  String? errorMessage;
  String weatherStatus = '맑음';
  double weatherTemp = 20;
  List<RestaurantItem> restaurants = [];

  // 카테고리 fallback 목록
  List<CategoryItem> availableCategories = const [
    CategoryItem(id: 1, name: '한식', imageAsset: 'assets/korean_food.png'),
    CategoryItem(id: 2, name: '중식', imageAsset: 'assets/chinese_food.png'),
    CategoryItem(id: 3, name: '일식', imageAsset: 'assets/japanese_food.png'),
    CategoryItem(id: 4, name: '아시안', imageAsset: 'assets/asian.png'),
    CategoryItem(id: 5, name: '패스트푸드', imageAsset: 'assets/fast_food.png'),
    CategoryItem(id: 6, name: '양식', imageAsset: 'assets/western_food.png'),
    CategoryItem(id: 7, name: '카페', imageAsset: 'assets/cafe.png'),
  ];

  @override
  void initState() {
    super.initState();
    _initialize();
  }

  @override
  void dispose() {
    _apiService.dispose();
    super.dispose();
  }

  Future<void> _initialize() async {
    // 앱 시작 시 카테고리 사전 조회
    try {
      final categories = await _apiService.fetchCategories();
      if (categories.isNotEmpty && mounted) {
        setState(() {
          availableCategories = categories;
        });
      }
    } catch (_) {
      // 카테고리 실패 시 기본 값 유지
    }

    await _fetchRestaurants(showLoading: true);
  }

  Future<void> _fetchRestaurants({required bool showLoading}) async {
    // 리스트 재조회
    if (showLoading && mounted) {
      setState(() {
        isLoading = true;
        errorMessage = null;
      });
    }

    try {
      // 요청 파라미터 구성
      final response = await _apiService.fetchRecommendations(
        RecommendationQuery(
          categoryIds: selectedCategories,
          minPrice: selectedPriceRange.start.toInt(),
          maxPrice: selectedPriceRange.end.toInt(),
          spicyLevel: currentSpiciness,
          weatherFilter: currentWeatherFilter,
          limit: 50,
        ),
      );

      if (!mounted) return;

      setState(() {
        // 성공 상태 반영
        restaurants = response.items;
        weatherStatus = response.weatherStatus;
        weatherTemp = response.weatherTemp;
        errorMessage = null;
      });
    } catch (e) {
      if (!mounted) return;
      final message = e is ApiException ? e.message : '네트워크 오류가 발생했습니다.';
      setState(() {
        // 실패 상태 반영
        restaurants = [];
        errorMessage = message;
      });
    } finally {
      if (mounted) {
        setState(() {
          isLoading = false;
        });
      }
    }
  }

  String formatKoreanPrice(double value) {
    // 원화 단위 문자열 변환
    final int price = value.toInt();
    if (price < 10000) return '${NumberFormat('#,###').format(price)}원';
    final int man = price ~/ 10000;
    final int rest = price % 10000;
    if (rest == 0) return '$man만원';
    return '$man만${NumberFormat('#,###').format(rest)}원';
  }

  String _displayCategoryName(RestaurantItem item) {
    // 카테고리명 fallback 처리
    final raw = item.categoryName?.trim() ?? '';
    if (raw.isNotEmpty && !raw.contains('?')) {
      return raw;
    }

    for (final category in availableCategories) {
      if (category.id == item.categoryId) {
        return category.name;
      }
    }
    return '';
  }

  Future<void> _resetFilters() async {
    // 필터 초기화
    setState(() {
      selectedCategories = [];
      selectedPriceRange = _defaultPriceRange;
      currentSpiciness = '';
      currentWeatherFilter = false;
    });
    await _fetchRestaurants(showLoading: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          Container(
            color: _delipickBlue,
            padding: const EdgeInsets.only(bottom: 15),
            child: Column(
              children: [
                SafeArea(
                  bottom: false,
                  child: Padding(
                    padding:
                        const EdgeInsets.symmetric(vertical: 5, horizontal: 16),
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: IconButton(
                            icon: const Icon(Icons.tune,
                                color: Colors.black, size: 28),
                            onPressed: () async {
                              final result = await Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (context) => FoodFilterScreen(
                                    initialSpiciness: currentSpiciness,
                                    initialWeather: currentWeatherFilter,
                                  ),
                                ),
                              );

                              if (result != null && result is Map) {
                                setState(() {
                                  currentSpiciness =
                                      result['spiciness'] as String? ?? '';
                                  currentWeatherFilter =
                                      result['weather'] as bool? ?? false;
                                });
                                await _fetchRestaurants(showLoading: true);
                              }
                            },
                          ),
                        ),
                        Center(
                          child: Image.asset(
                            'assets/delipick_logo.png',
                            height: 70,
                            fit: BoxFit.contain,
                            errorBuilder: (context, error, stackTrace) => const Text(
                              'Delipick',
                              style: TextStyle(
                                fontSize: 24,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Container(
                    height: 45,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Row(
                      children: [
                        SizedBox(width: 12),
                        Icon(Icons.location_on_outlined,
                            color: Colors.grey, size: 20),
                        SizedBox(width: 8),
                        Text(
                          '동아대 승학캠퍼스',
                          style: TextStyle(fontSize: 15, color: Colors.black),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Align(
              alignment: Alignment.centerLeft,
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  children: [
                    GestureDetector(
                      onTap: _resetFilters,
                      child: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          border: Border.all(color: Colors.grey[300]!),
                          shape: BoxShape.circle,
                        ),
                        child:
                            Icon(Icons.refresh, size: 20, color: Colors.grey[700]),
                      ),
                    ),
                    const SizedBox(width: 8),
                    _buildCategoryButton(),
                    const SizedBox(width: 8),
                    _buildPriceButton(),
                    const SizedBox(width: 8),
                  ],
                ),
              ),
            ),
          ),
          if (currentWeatherFilter)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  '날씨: $weatherStatus ${weatherTemp.toStringAsFixed(1)}°C',
                  style: const TextStyle(fontSize: 13, color: Colors.grey),
                ),
              ),
            ),
          Expanded(child: _buildRestaurantSection()),
        ],
      ),
    );
  }

  Widget _buildCategoryButton() {
    // 카테고리 바텀시트
    final bool isActive = selectedCategories.isNotEmpty;
    return GestureDetector(
      onTap: () async {
        final result = await showModalBottomSheet<List<int>>(
          context: context,
          isScrollControlled: true,
          backgroundColor: Colors.transparent,
          builder: (context) => CategorySheet(
            initialSelected: selectedCategories,
            availableCategories: availableCategories,
          ),
        );

        if (result != null) {
          setState(() => selectedCategories = result);
          await _fetchRestaurants(showLoading: true);
        }
      },
      child: _buildFilterButton(
        Icons.restaurant_menu,
        isActive ? '카테고리(${selectedCategories.length})' : '카테고리',
        isActive,
      ),
    );
  }

  Widget _buildPriceButton() {
    // 가격 바텀시트
    final bool isActive = !(selectedPriceRange.start == 2000 &&
        selectedPriceRange.end == 100000);

    return GestureDetector(
      onTap: () async {
        final result = await showModalBottomSheet<RangeValues>(
          context: context,
          isScrollControlled: true,
          backgroundColor: Colors.transparent,
          builder: (context) => PriceRangeSheet(initialRange: selectedPriceRange),
        );

        if (result != null) {
          setState(() => selectedPriceRange = result);
          await _fetchRestaurants(showLoading: true);
        }
      },
      child: _buildFilterButton(
        Icons.monetization_on_outlined,
        isActive
            ? '${formatKoreanPrice(selectedPriceRange.start)}-${formatKoreanPrice(selectedPriceRange.end)}'
            : '가격대',
        isActive,
      ),
    );
  }

  Widget _buildFilterButton(IconData icon, String label, bool isActive) {
    // 공통 필터 칩
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: isActive ? const Color(0xFFE3F2FD) : Colors.white,
        border: Border.all(
          color: isActive ? Colors.blue : Colors.grey[300]!,
          width: 1.2,
        ),
        borderRadius: BorderRadius.circular(25),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: isActive ? Colors.blue : Colors.grey[700]),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              fontSize: 14,
              color: isActive ? Colors.blue : Colors.grey[800],
              fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          const Icon(Icons.keyboard_arrow_down, size: 18, color: Colors.grey),
        ],
      ),
    );
  }

  Widget _buildRestaurantSection() {
    // 로딩 상태
    if (isLoading) {
      return const Center(child: CircularProgressIndicator(color: _delipickBlue));
    }

    // 에러 상태
    if (errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('데이터를 불러오지 못했습니다.'),
              const SizedBox(height: 8),
              Text(
                errorMessage!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.grey, fontSize: 12),
              ),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => _fetchRestaurants(showLoading: true),
                style: ElevatedButton.styleFrom(backgroundColor: _delipickBlue),
                child: const Text(
                  '다시 시도',
                  style: TextStyle(color: Colors.black),
                ),
              ),
            ],
          ),
        ),
      );
    }

    // 빈 결과 상태
    if (restaurants.isEmpty) {
      return const Center(
        child: Text(
          '조건에 맞는 식당이 없습니다.',
          style: TextStyle(color: Colors.grey),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: () => _fetchRestaurants(showLoading: false),
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: restaurants.length,
        itemBuilder: (context, index) => _buildRestaurantCard(restaurants[index]),
      ),
    );
  }

  Widget _buildRestaurantCard(RestaurantItem item) {
    // 식당 카드
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(8),
        boxShadow: const [
          BoxShadow(color: Colors.black12, blurRadius: 3, offset: Offset(0, 1)),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 90,
            height: 90,
            margin: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.grey[300],
              borderRadius: BorderRadius.circular(8),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: item.imageUrl == null || item.imageUrl!.isEmpty
                  ? const Icon(Icons.fastfood, color: Colors.white)
                  : Image.network(
                      item.imageUrl!,
                      fit: BoxFit.cover,
                      errorBuilder: (context, error, stackTrace) =>
                          const Icon(Icons.fastfood, color: Colors.white),
                    ),
            ),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      const Icon(Icons.star, color: Colors.orange, size: 18),
                      const SizedBox(width: 2),
                      Text(item.rating.toStringAsFixed(1)),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          _displayCategoryName(item),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style:
                              const TextStyle(fontSize: 12, color: Colors.grey),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    item.mainMenuPrice == null
                        ? (item.mainMenu ?? '-')
                        : '${item.mainMenu ?? '-'} · ${NumberFormat('#,###').format(item.mainMenuPrice)}원',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13, color: Colors.black87),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.fromLTRB(10, 6, 12, 6),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE3F2FD),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      '예상 배달 시간: ${item.estimatedTotalTime.toStringAsFixed(0)}분',
                      style: const TextStyle(
                        fontSize: 13,
                        color: Colors.black,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
