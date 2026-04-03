import 'package:flutter/material.dart';

class CategorySheet extends StatefulWidget {
  final List<String> initialSelected;

  const CategorySheet({super.key, required this.initialSelected});

  @override
  State<CategorySheet> createState() => _CategorySheetState();
}

class _CategorySheetState extends State<CategorySheet> {
  late List<String> tempSelected;

  final List<Map<String, String>> categories = [
    {'name': '한식', 'image': 'assets/korean_food.png'},
    {'name': '중식', 'image': 'assets/chinese_food.png'},
    {'name': '일식', 'image': 'assets/japanese_food.png'},
    {'name': '아시안', 'image': 'assets/asian.png'},
    {'name': '패스트푸드', 'image': 'assets/fast_food.png'},
    {'name': '양식', 'image': 'assets/western_food.png'},
    {'name': '카페/디저트', 'image': 'assets/cafe.png'},
  ];

  @override
  void initState() {
    super.initState();
    tempSelected = List.from(widget.initialSelected);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.5,
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(30),
          topRight: Radius.circular(30),
        ),
      ),
      child: Column(
        children: [
          const SizedBox(height: 20),
          const Text(
            '카테고리',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const Divider(indent: 20, endIndent: 20),

          // ✅ GridView 영역: 오버플로우 방지를 위해 Expanded로 감쌈
          Expanded(
            child: GridView.builder(
              padding: const EdgeInsets.all(20),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 4,
                mainAxisSpacing: 15,
                crossAxisSpacing: 15,
                childAspectRatio: 0.8, // 👈 높이 비율을 살짝 늘려 공간 확보
              ),
              itemCount: categories.length,
              itemBuilder: (context, index) {
                final cat = categories[index];
                final isSelected = tempSelected.contains(cat['name']);

                return GestureDetector(
                  onTap: () {
                    setState(() {
                      if (isSelected) {
                        tempSelected.remove(cat['name']);
                      } else {
                        tempSelected.add(cat['name']!);
                      }
                    });
                  },
                  child: Container(
                    decoration: BoxDecoration(
                      color: isSelected ? const Color(0xFFE3F2FD) : Colors.white,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: isSelected ? const Color(0xFF64B5F6) : Colors.transparent,
                        width: 2,
                      ),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        // ✅ 아이콘 크기 제한
                        Flexible(
                          child: Image.asset(
                            cat['image']!,
                            width: 45,
                            height: 45,
                            errorBuilder: (context, error, stackTrace) =>
                            const Icon(Icons.restaurant, size: 40, color: Colors.grey),
                          ),
                        ),
                        const SizedBox(height: 8),
                        // ✅ 글자가 넘치지 않게 FittedBox 사용
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(
                            cat['name']!,
                            style: TextStyle(
                              fontSize: 13,
                              color: Colors.black,
                              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),

          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 5, 20, 15),
              child: SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: () => Navigator.pop(context, tempSelected),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF64B5F6),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                  child: const Text(
                    '확인',
                    style: TextStyle(
                      fontSize: 18,
                      color: Colors.black,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}