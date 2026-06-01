import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'cart_screen.dart';
import 'food_list_category.dart';
import 'food_list_price.dart';
import 'menu_list_screen.dart';
import 'models/cart.dart';
import 'models/restaurant.dart';
import 'services/api_service.dart';
import 'taste_preference.dart';

class FoodListScreen extends StatefulWidget {
  const FoodListScreen({super.key});

  @override
  State<FoodListScreen> createState() => _FoodListScreenState();
}

class _FoodListScreenState extends State<FoodListScreen> {
  static const RangeValues _defaultPriceRange = RangeValues(2000, 100000);
  static const Color _delipickBlue = Color(0xFF64B5F6);

  final DelipickApiService _apiService = DelipickApiService();

  List<int> selectedCategories = [];
  RangeValues selectedPriceRange = _defaultPriceRange;
  String currentUserType = '';
  String currentPreferenceText = '';

  // 각 맛의 세부 조절 단계 관리 (0: 낮음, 1: 중간, 2: 높음)
  // 기본 중간 (아무것도 선택X)
  Map<String, int> currentTasteLevels = {
    'salty': 1,
    'sweet': 1,
    'sour': 1,
    'spicy': 1,
    'umami': 1,
  };

  bool isLoading = true;
  String? errorMessage;
  String currentMode = 'default_delivery';
  List<RestaurantItem> restaurants = [];

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
    try {
      final categories = await _apiService.fetchCategories();
      if (categories.isNotEmpty && mounted) {
        setState(() {
          availableCategories = categories;
        });
      }
    } catch (_) {
      // API 조회 실패 시 하드코딩된 대안 상수를 유지하기 위한 예외 방어
    }

    await _fetchRestaurants(showLoading: true);
  }

  Future<void> _fetchRestaurants({required bool showLoading}) async {
    if (showLoading && mounted) {
      setState(() {
        isLoading = true;
        errorMessage = null;
      });
    }

    try {
      final response = await _apiService.fetchRecommendations(
        RecommendationQuery(
          categoryIds: selectedCategories,
          minPrice: selectedPriceRange.start.toInt(),
          maxPrice: selectedPriceRange.end.toInt(),
          userType: currentUserType,
          preferenceText: currentPreferenceText,
          limit: 50,
        ),
      );

      if (!mounted) return;

      setState(() {
        restaurants = response.items;
        currentMode = response.mode;
        errorMessage = null;
      });
    } catch (e) {
      if (!mounted) return;
      final message = e is ApiException ? e.message : '네트워크 오류가 발생했습니다.';
      setState(() {
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
    final int price = value.toInt();
    if (price < 10000) return '${NumberFormat('#,###').format(price)}원';
    final int man = price ~/ 10000;
    final int rest = price % 10000;
    if (rest == 0) return '$man만원';
    return '$man만${NumberFormat('#,###').format(rest)}원';
  }

  String _displayCategoryName(RestaurantItem item) {
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

  String _userTypeLabel(String type) {
    switch (type) {
      case 'convenience':
        return '편의형';
      case 'gourmet':
        return '미식형';
      case 'budget':
        return '경제형';
      default:
        return '미선택';
    }
  }

  Future<void> _resetFilters() async {
    setState(() {
      selectedCategories = [];
      selectedPriceRange = _defaultPriceRange;
      currentUserType = '';
      currentPreferenceText = '';
      currentMode = 'default_delivery';
      currentTasteLevels = {
        'salty': 1,
        'sweet': 1,
        'sour': 1,
        'spicy': 1,
        'umami': 1,
      };
    });
    await _fetchRestaurants(showLoading: true);
  }

  @override
  Widget build(BuildContext context) {
    // 상단 텍스트 출력용 상태 활성화 여부 계산
    final bool hasUserType = currentUserType.isNotEmpty;
    // 모든 맛 레벨 중 하나라도 기본값(1)에서 어긋났는지 검증하여 변경 여부 판단
    final bool hasCustomTaste = currentTasteLevels.values.any((level) => level != 1);

    // 요구사항에 맞춰 자연어 입력(PreferenceText) 유무는 상단 라벨 활성화 조건에서 영구 배제
    final bool showFilterLabel = hasUserType || hasCustomTaste;

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
                    padding: const EdgeInsets.symmetric(vertical: 5, horizontal: 16),
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: IconButton(
                            icon: const Icon(Icons.settings_outlined,
                                color: Colors.black, size: 28),
                            onPressed: () async {
                              final result = await Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (context) => TastePreferenceScreen(
                                    initialUserType: currentUserType,
                                    initialPreferenceText: currentPreferenceText,
                                    initialTasteLevels: currentTasteLevels,
                                  ),
                                ),
                              );

                              if (result != null && result is Map) {
                                setState(() {
                                  currentUserType = result['userType'] as String? ?? '';
                                  currentPreferenceText = result['preferenceText'] as String? ?? '';
                                  if (result['tasteLevels'] != null) {
                                    currentTasteLevels = Map<String, int>.from(result['tasteLevels'] as Map);
                                  }
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
                        // 장바구니 아이콘 (헤더 오른쪽 끝)
                        Align(
                          alignment: Alignment.centerRight,
                          child: ListenableBuilder(
                            listenable: cartModel,
                            builder: (context, _) {
                              final count = cartModel.totalCount;
                              return Stack(
                                clipBehavior: Clip.none,
                                children: [
                                  IconButton(
                                    icon: const Icon(
                                      Icons.shopping_cart_outlined,
                                      color: Colors.black,
                                      size: 28,
                                    ),
                                    onPressed: () {
                                      Navigator.push(
                                        context,
                                        MaterialPageRoute(
                                          builder: (context) => const CartScreen(),
                                        ),
                                      );
                                    },
                                  ),
                                  if (count > 0)
                                    Positioned(
                                      top: 4,
                                      right: 4,
                                      child: Container(
                                        width: 18,
                                        height: 18,
                                        decoration: const BoxDecoration(
                                          color: Colors.red,
                                          shape: BoxShape.circle,
                                        ),
                                        alignment: Alignment.center,
                                        child: Text(
                                          count > 99 ? '99+' : '$count',
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontSize: 10,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ),
                                    ),
                                ],
                              );
                            },
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
                        Icon(Icons.location_on_outlined, color: Colors.grey, size: 20),
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
                        child: Icon(Icons.refresh, size: 20, color: Colors.grey[700]),
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

          // 사용자 유형 및 맛 조절 상태를 기반으로 동적 라벨 결합 및 노출
          if (showFilterLabel)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Builder(
                  builder: (context) {
                    List<String> labels = [];

                    // 사용자 유형이 선택되었을 경우 텍스트 추가
                    if (hasUserType) {
                      labels.add(_userTypeLabel(currentUserType));
                    }

                    // 맛 조절 단계 변경 시 문구 추가
                    if (hasCustomTaste) {
                      labels.add('맛 적용 중');
                    }

                    // 두 조건 모두 해당할 시 ' · ' 로 결합 (e.g. 편의형 · 맛 적용 중)
                    return Text(
                      labels.join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 13, color: Colors.grey),
                    );
                  },
                ),
              ),
            ),

          // 설정값 유무가 전혀 체크되지 않은 초기 default 상태 분기
          if (!showFilterLabel)
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 0, 16, 10),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  '기본 정렬: 배달 빠른 순',
                  style: TextStyle(fontSize: 13, color: Colors.grey),
                ),
              ),
            ),

          Expanded(child: _buildRestaurantSection()),
        ],
      ),
    );
  }

  Widget _buildCategoryButton() {
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
    final bool isActive = !(selectedPriceRange.start == 2000 && selectedPriceRange.end == 100000);

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
    if (isLoading) {
      return const Center(child: CircularProgressIndicator(color: _delipickBlue));
    }

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

    if (restaurants.isEmpty) {
      return Center(
        child: Text(
          currentMode == 'personalized' ? '조건에 맞는 음식이 없습니다.' : '조건에 맞는 식당이 없습니다.',
          style: const TextStyle(color: Colors.grey),
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
    return GestureDetector(
      onTap: () {
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => MenuListScreen(
              restaurantId: item.id,
              restaurantName: item.restaurantName ?? item.name,
              deliveryTime: item.estimatedTotalTime.round(),
            ),
          ),
        );
      },
      child: Container(
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
                    if (currentMode == 'personalized' && (item.restaurantName ?? '').isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          item.restaurantName!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12, color: Colors.grey),
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
                            style: const TextStyle(fontSize: 12, color: Colors.grey),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      currentMode == 'personalized'
                          ? (item.mainMenuPrice == null
                          ? '-'
                          : '${NumberFormat('#,###').format(item.mainMenuPrice)}원')
                          : (item.mainMenuPrice == null
                          ? (item.mainMenu ?? '-')
                          : '${item.mainMenu ?? '-'} · ${NumberFormat('#,###').format(item.mainMenuPrice)}원'),
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
                    if (currentMode == 'personalized' && (item.recommendationReason ?? '').isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 6),
                        child: Text(
                          item.recommendationReason!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 12, color: Colors.grey),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}