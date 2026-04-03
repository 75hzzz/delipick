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
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              const Text(
                '카테고리',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(width: 4),
              Text(
                '(복수)',
                style: TextStyle(color: Colors.grey[600], fontSize: 14),
              ),
            ],
          ),
          const Divider(indent: 20, endIndent: 20),

          Expanded(
            child: GridView.builder(
              shrinkWrap: true,
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 4,
                mainAxisSpacing: 10,
                crossAxisSpacing: 10,
                childAspectRatio: 0.85,
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
                      color: isSelected ? Colors.grey[300] : Colors.grey[100],
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        // 선택 시 테두리도 조금 더 진한 회색으로 강조
                        color: isSelected ? Colors.grey[600]! : Colors.transparent,
                        width: 2,
                      ),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Image.asset(
                          cat['image']!,
                          height: 65,
                          width: 65,
                          errorBuilder: (c, e, s) => const Icon(Icons.fastfood),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          cat['name']!,
                          style: TextStyle(
                            fontSize: 13,
                            color: Colors.black,
                            fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
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