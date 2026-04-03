import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'food_list_category.dart';
import 'food_list_price.dart';
import 'food_filter.dart';

class FoodListScreen extends StatefulWidget {
  const FoodListScreen({super.key});

  @override
  State<FoodListScreen> createState() => _FoodListScreenState();
}

class _FoodListScreenState extends State<FoodListScreen> {
  // 상태 변수 관리
  List<String> selectedCategories = [];
  RangeValues selectedPriceRange = const RangeValues(2000, 100000);

  // 상세 필터용 상태 변수 (여기서 관리함)
  String currentSpiciness = '';
  bool currentWeatherFilter = false;

  String formatKoreanPrice(double value) {
    int price = value.toInt();
    if (price < 10000) return '${NumberFormat('#,###').format(price)}원';
    int man = price ~/ 10000;
    int rest = price % 10000;
    if (rest == 0) return '$man만 원';
    return '$man만 ${NumberFormat('#,###').format(rest)}원';
  }

  void _resetFilters() {
    setState(() {
      selectedCategories = [];
      selectedPriceRange = const RangeValues(2000, 100000);
      currentSpiciness = '';
      currentWeatherFilter = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    const Color delipickBlue = Color(0xFF64B5F6); //앱 테마색

    return Scaffold(
      body: Column(
        children: [
          // 상단 파란색 영역
          Container(
            color: delipickBlue,
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
                        // 상세 필터 버튼
                        Align(
                          alignment: Alignment.centerLeft,
                          child: IconButton(
                            icon: const Icon(Icons.tune, color: Colors.black, size: 28),
                            onPressed: () async {
                              // 상세 필터 화면으로 이동하며 현재 값을 넘겨줌
                              final result = await Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (context) => FoodFilterScreen(
                                    initialSpiciness: currentSpiciness,
                                    initialWeather: currentWeatherFilter,
                                  ),
                                ),
                              );

                              // 돌아왔을 때 결과 데이터가 있으면 리스트 화면의 상태를 업데이트함
                              if (result != null && result is Map) {
                                setState(() {
                                  currentSpiciness = result['spiciness'];
                                  currentWeatherFilter = result['weather'];
                                });
                                debugPrint('필터 적용 완료: $currentSpiciness, $currentWeatherFilter');
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
                              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.white),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                // 주소창
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Container(
                    height: 45,
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(4)),
                    child: Row(
                      children: const [
                        SizedBox(width: 12),
                        Icon(Icons.location_on_outlined, color: Colors.grey, size: 20),
                        SizedBox(width: 8),
                        Text('동아대 승학캠퍼스', style: TextStyle(fontSize: 15, color: Colors.black)),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),

          // 필터 버튼 영역
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
                        decoration: BoxDecoration(color: Colors.white, border: Border.all(color: Colors.grey[300]!), shape: BoxShape.circle),
                        child: Icon(Icons.refresh, size: 20, color: Colors.grey[700]),
                      ),
                    ),
                    const SizedBox(width: 8),
                    _buildCategoryButton(),
                    const SizedBox(width: 8),
                    _buildPriceButton(),
                  ],
                ),
              ),
            ),
          ),

          // 음식점 리스트 영역
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              children: [
                _buildRestaurantCard(name: '음식점1', rating: 3.5, deliveryTime: 20),
                _buildRestaurantCard(name: '음식점2', rating: 4.9, deliveryTime: 25),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // 필터 버튼 빌더 위젯들
  Widget _buildCategoryButton() {
    bool isActive = selectedCategories.isNotEmpty;
    return GestureDetector(
      onTap: () async {
        final result = await showModalBottomSheet<List<String>>(
          context: context,
          isScrollControlled: true,
          backgroundColor: Colors.transparent,
          builder: (context) => CategorySheet(initialSelected: selectedCategories),
        );
        if (result != null) setState(() => selectedCategories = result);
      },
      child: _buildFilterButton(Icons.restaurant_menu, isActive ? '카테고리(${selectedCategories.length})' : '카테고리', isActive),
    );
  }

  Widget _buildPriceButton() {
    bool isActive = !(selectedPriceRange.start == 2000 && selectedPriceRange.end == 100000);
    return GestureDetector(
      onTap: () async {
        final result = await showModalBottomSheet<RangeValues>(
          context: context,
          isScrollControlled: true,
          backgroundColor: Colors.transparent,
          builder: (context) => PriceRangeSheet(initialRange: selectedPriceRange),
        );
        if (result != null) setState(() => selectedPriceRange = result);
      },
      child: _buildFilterButton(Icons.monetization_on_outlined, isActive ? '${formatKoreanPrice(selectedPriceRange.start)}-${formatKoreanPrice(selectedPriceRange.end)}' : '가격범위', isActive),
    );
  }

  Widget _buildFilterButton(IconData icon, String label, bool isActive) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: isActive ? const Color(0xFFE3F2FD) : Colors.white,
        border: Border.all(color: isActive ? Colors.blue : Colors.grey[300]!, width: 1.2),
        borderRadius: BorderRadius.circular(25),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: isActive ? Colors.blue : Colors.grey[700]),
          const SizedBox(width: 6),
          Text(label, style: TextStyle(fontSize: 14, color: isActive ? Colors.blue : Colors.grey[800], fontWeight: isActive ? FontWeight.bold : FontWeight.normal)),
          const Icon(Icons.keyboard_arrow_down, size: 18, color: Colors.grey),
        ],
      ),
    );
  }

  Widget _buildRestaurantCard({required String name, required double rating, required int deliveryTime}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(8), boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 3, offset: Offset(0, 1))]),
      child: Row(
        children: [
          Container(width: 90, height: 90, margin: const EdgeInsets.all(12), decoration: BoxDecoration(color: Colors.grey[300], borderRadius: BorderRadius.circular(8))),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                Row(
                  children: [
                    const Icon(Icons.star, color: Colors.orange, size: 18),
                    Text(rating.toString()),
                    // 거리(distance) 아이콘과 텍스트 영역을 삭제했습니다.
                  ],
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.fromLTRB(10, 6, 12, 6),
                  decoration: BoxDecoration(color: const Color(0xFFE3F2FD), borderRadius: BorderRadius.circular(4)),
                  child: Text('현재 예상 배달 시간 : $deliveryTime분', style: const TextStyle(fontSize: 13, color: Colors.black, fontWeight: FontWeight.w500)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}