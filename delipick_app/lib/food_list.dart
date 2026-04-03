import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'food_list_category.dart';
import 'food_list_price.dart';
import 'food_filter.dart'; // 이 경로가 정확해야 FoodFilterScreen을 인식합니다.
import 'restaurant_model.dart';

class FoodListScreen extends StatefulWidget {
  const FoodListScreen({super.key});

  @override
  State<FoodListScreen> createState() => _FoodListScreenState();
}

class _FoodListScreenState extends State<FoodListScreen> {
  List<String> selectedCategories = [];
  RangeValues selectedPriceRange = const RangeValues(2000, 100000);
  String currentSpiciness = '';
  bool currentWeatherFilter = false;

  List<Restaurant> restaurants = [];
  bool isLoading = false;

  @override
  void initState() {
    super.initState();
    _fetchRestaurants();
  }

  Future<void> _fetchRestaurants() async {
    setState(() => isLoading = true);

    // 카테고리 매핑 로직
    Map<String, int> categoryMap = {
      '한식': 1, '중식': 2, '일식': 3, '아시안': 4, '패스트푸드': 5, '양식': 6, '카페/디저트': 7
    };
    List<int> prefs = selectedCategories.map((e) => categoryMap[e] ?? 0).toList();

    // 맵기 단계 변환 (중괄호 오류 수정 완료)
    String spicyLevel = "0";
    if (currentSpiciness == '순한맛') {
      spicyLevel = "1";
    } else if (currentSpiciness == '중간맛') {
      spicyLevel = "2";
    } else if (currentSpiciness == '매운맛') {
      spicyLevel = "3";
    }

    try {
      // 이미지상의 IP 주소(172.27.126.107)를 유지합니다.
      final baseUrl = "http://172.27.126.107:8000/api/recommend";
      final queryParams = {
        'spicy': spicyLevel,
        'min_price': selectedPriceRange.start.toInt().toString(),
        'max_price': selectedPriceRange.end.toInt().toString(),
        'prefs': prefs.isEmpty
            ? [1, 2, 3, 4, 5, 6, 7].map((e) => e.toString()).toList()
            : prefs.map((e) => e.toString()).toList(),
      };

      final uri = Uri.parse(baseUrl).replace(queryParameters: queryParams);
      final response = await http.get(uri);

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes));
        if (data['success']) {
          setState(() {
            restaurants = (data['data'] as List)
                .map((json) => Restaurant.fromJson(json))
                .toList();
          });
        }
      }
    } catch (e) {
      debugPrint("데이터 로딩 실패: $e");
    } finally {
      setState(() => isLoading = false);
    }
  }

  void _resetFilters() {
    setState(() {
      selectedCategories = [];
      selectedPriceRange = const RangeValues(2000, 100000);
      currentSpiciness = '';
      currentWeatherFilter = false;
    });
    _fetchRestaurants();
  }

  @override
  Widget build(BuildContext context) {
    const Color delipickBlue = Color(0xFF64B5F6);

    return Scaffold(
      backgroundColor: Colors.white,
      body: Column(
        children: [
          _buildTopBanner(delipickBlue),
          _buildFilterBar(),
          Expanded(
            child: isLoading
                ? const Center(child: CircularProgressIndicator())
                : restaurants.isEmpty
                ? const Center(child: Text("조건에 맞는 식당이 없어요!"))
                : ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: restaurants.length,
              itemBuilder: (context, index) => _buildRestaurantCard(restaurants[index]),
            ),
          ),
        ],
      ),
    );
  }

  // 상단 배너 및 필터 바 위젯 생략 (기본 디자인 유지)
  Widget _buildTopBanner(Color color) {
    return Container(
      color: color,
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
                      icon: const Icon(Icons.tune, color: Colors.black, size: 28),
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
                        if (result != null) {
                          setState(() {
                            currentSpiciness = result['spiciness'];
                            currentWeatherFilter = result['weather'];
                          });
                          _fetchRestaurants();
                        }
                      },
                    ),
                  ),
                  const Text('delipick', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: Colors.white)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16),
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
    );
  }

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
        if (result != null) {
          setState(() => selectedCategories = result);
          _fetchRestaurants();
        }
      },
      child: _buildFilterBtn(Icons.restaurant_menu, isActive ? '카테고리(${selectedCategories.length})' : '카테고리', isActive),
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
        if (result != null) {
          setState(() => selectedPriceRange = result);
          _fetchRestaurants();
        }
      },
      child: _buildFilterBtn(Icons.monetization_on_outlined, isActive ? '가격 설정됨' : '가격범위', isActive),
    );
  }

  Widget _buildFilterBtn(IconData icon, String label, bool isActive) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: isActive ? const Color(0xFFE3F2FD) : Colors.white,
        border: Border.all(color: isActive ? Colors.blue : Colors.grey[300]!, width: 1.2),
        borderRadius: BorderRadius.circular(25),
      ),
      child: Row(children: [
        Icon(icon, size: 18, color: isActive ? Colors.blue : Colors.grey[700]),
        const SizedBox(width: 6),
        Text(label, style: TextStyle(fontSize: 14, color: isActive ? Colors.blue : Colors.grey[800], fontWeight: isActive ? FontWeight.bold : FontWeight.normal)),
      ]),
    );
  }

  Widget _buildRestaurantCard(Restaurant res) {
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
                Text(res.name, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                Text(res.mainMenu, style: TextStyle(fontSize: 13, color: Colors.grey[600])),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(color: const Color(0xFFE3F2FD), borderRadius: BorderRadius.circular(4)),
                  child: Text('배달 시간: ${res.deliveryTime}분 | 점수: ${res.score.toInt()}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}