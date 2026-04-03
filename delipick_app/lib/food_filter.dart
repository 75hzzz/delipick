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
  late String selectedSpiciness;
  late bool isWeatherFilterOn;
  final List<String> spicinessLevels = ['순한맛', '중간맛', '매운맛'];

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
        title: const Text('상세 취향 설정', style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold)),
        centerTitle: true,
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          children: [
            const SizedBox(height: 30),
            _buildSpicySection(),
            const SizedBox(height: 40),
            _buildWeatherSection(),
            const Spacer(),
            _buildConfirmButton(),
          ],
        ),
      ),
    );
  }

  Widget _buildSpicySection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(children: [
          Icon(Icons.local_fire_department_outlined),
          SizedBox(width: 5),
          Text('맵기 설정', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        ]),
        const SizedBox(height: 15),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: spicinessLevels.map((level) => _buildSpicyChip(level)).toList(),
        ),
      ],
    );
  }

  Widget _buildSpicyChip(String label) {
    bool isSelected = selectedSpiciness == label;
    return GestureDetector(
      onTap: () => setState(() => selectedSpiciness = isSelected ? '' : label),
      child: Container(
        width: MediaQuery.of(context).size.width * 0.28,
        height: 48,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: isSelected ? Colors.grey[300] : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: isSelected ? Colors.grey[600]! : Colors.grey[300]!),
        ),
        child: Text(label, style: TextStyle(fontWeight: isSelected ? FontWeight.bold : FontWeight.normal)),
      ),
    );
  }

  Widget _buildWeatherSection() {
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(color: const Color(0xFFE3F2FD), borderRadius: BorderRadius.circular(10)),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text('날씨 필터 적용', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          Switch(
            value: isWeatherFilterOn,
            activeColor: const Color(0xFF64B5F6),
            onChanged: (val) => setState(() => isWeatherFilterOn = val),
          ),
        ],
      ),
    );
  }

  Widget _buildConfirmButton() {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.only(bottom: 20),
        child: SizedBox(
          width: double.infinity,
          height: 55,
          child: ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF64B5F6), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(15))),
            onPressed: () => Navigator.pop(context, {'spiciness': selectedSpiciness, 'weather': isWeatherFilterOn}),
            child: const Text('내 취향 음식점 보기', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black)),
          ),
        ),
      ),
    );
  }
}