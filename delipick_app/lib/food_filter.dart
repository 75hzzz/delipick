import 'package:flutter/material.dart';

class FoodFilterScreen extends StatefulWidget {
  final String initialSpiciness;
  final bool initialWeather;

  const FoodFilterScreen({
    super.key,
    required this.initialSpiciness,
    required this.initialWeather,
  });

  @override
  State<FoodFilterScreen> createState() => _FoodFilterScreenState();
}

class _FoodFilterScreenState extends State<FoodFilterScreen> {
  // 현재 선택 상태
  late String selectedSpiciness;
  late bool isWeatherFilterOn;

  // 맵기 옵션 목록
  final List<Map<String, String>> spicinessLevels = const [
    {'key': 'mild', 'label': '순한맛'},
    {'key': 'medium', 'label': '중간맛'},
    {'key': 'hot', 'label': '매운맛'},
  ];

  @override
  void initState() {
    super.initState();
    selectedSpiciness = widget.initialSpiciness;
    isWeatherFilterOn = widget.initialWeather;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.black, size: 30),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          '상세 취향 설정',
          style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(color: Colors.grey[300], height: 1.0),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(height: 40),
            Row(
              children: [
                const Icon(Icons.local_fire_department_outlined,
                    color: Colors.black),
                const SizedBox(width: 5),
                const Text(
                  '맵기 설정',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const SizedBox(width: 8),
                Text(
                  '(단일)',
                  style: TextStyle(color: Colors.grey[600], fontSize: 14),
                ),
              ],
            ),
            const SizedBox(height: 15),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: spicinessLevels
                  .map((level) => _buildSpicyButton(level['key']!, level['label']!))
                  .toList(),
            ),
            const SizedBox(height: 40),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFFE3F2FD),
                borderRadius: BorderRadius.circular(10),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.1),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    '날씨 필터 적용',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  Switch(
                    value: isWeatherFilterOn,
                    activeThumbColor: Colors.white,
                    activeTrackColor: const Color(0xFF64B5F6),
                    onChanged: (value) {
                      setState(() {
                        isWeatherFilterOn = value;
                      });
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            const Padding(
              padding: EdgeInsets.only(left: 5),
              child: Text(
                '현재 날씨에 어울리는 음식 추천을 반영합니다.',
                style: TextStyle(color: Colors.grey, fontSize: 14),
              ),
            ),
            const Spacer(),
            SafeArea(
              child: Padding(
                padding: const EdgeInsets.only(bottom: 20),
                child: SizedBox(
                  width: double.infinity,
                  height: 55,
                  child: ElevatedButton(
                    onPressed: () {
                      Navigator.pop(context, {
                        'spiciness': selectedSpiciness,
                        'weather': isWeatherFilterOn,
                      });
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF64B5F6),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(15),
                      ),
                      elevation: 0,
                    ),
                    child: const Text(
                      '이 취향으로 보기',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: Colors.black,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSpicyButton(String key, String label) {
    // 맵기 선택 버튼
    final isSelected = selectedSpiciness == key;
    return GestureDetector(
      onTap: () {
        setState(() {
          selectedSpiciness = isSelected ? '' : key;
        });
      },
      child: Container(
        width: MediaQuery.of(context).size.width * 0.28,
        height: 48,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: isSelected ? Colors.grey[300] : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? Colors.grey[600]! : Colors.grey[300]!,
            width: 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 4,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Text(
          label,
          style: TextStyle(
            color: Colors.black,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}
