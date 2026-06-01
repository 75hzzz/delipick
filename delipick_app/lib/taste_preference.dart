import 'package:flutter/material.dart';

class TastePreferenceScreen extends StatefulWidget {
  final String initialUserType;
  final String initialPreferenceText;
  final Map<String, int>? initialTasteLevels;

  const TastePreferenceScreen({
    super.key,
    required this.initialUserType,
    required this.initialPreferenceText,
    this.initialTasteLevels,
  });

  @override
  State<TastePreferenceScreen> createState() => _TastePreferenceScreenState();
}

class _TastePreferenceScreenState extends State<TastePreferenceScreen> {
  late String selectedUserType;
  late TextEditingController preferenceController;

  // 메인 화면과의 데이터 맵핑 및 루프 생성용 Key-Label 데이터셋
  final List<Map<String, String>> tasteCategories = const [
    {'key': 'salty', 'label': '짠맛'},
    {'key': 'sweet', 'label': '단맛'},
    {'key': 'sour', 'label': '신맛'},
    {'key': 'spicy', 'label': '매운맛'},
    {'key': 'umami', 'label': '감칠맛'},
  ];

  // 상단 바인딩 및 슬라이더 제어용 맛 단계 데이터 (0: 낮음, 1: 중간, 2: 높음)
  late Map<String, int> tasteLevels;

  final List<Map<String, dynamic>> userTypes = const [
    {
      'key': 'convenience',
      'label': '편의형',
      'sub': '빠르고\n간단하게',
      'icon': Icons.access_time_rounded
    },
    {
      'key': 'gourmet',
      'label': '미식형',
      'sub': '꼼꼼하고\n맛있게',
      'icon': Icons.restaurant_rounded
    },
    {
      'key': 'budget',
      'label': '경제형',
      'sub': '합리적이고\n알뜰하게',
      'icon': Icons.local_offer_rounded
    },
  ];

  @override
  void initState() {
    super.initState();
    selectedUserType = widget.initialUserType;
    preferenceController = TextEditingController(text: widget.initialPreferenceText);

    // Deep Copy를 통해 이전 화면의 상태 오염 방지 및 초기 Null 예외 처리
    tasteLevels = widget.initialTasteLevels != null
        ? Map<String, int>.from(widget.initialTasteLevels!)
        : {
      'salty': 1,
      'sweet': 1,
      'sour': 1,
      'spicy': 1,
      'umami': 1,
    };
  }

  @override
  void dispose() {
    preferenceController.dispose();
    super.dispose();
  }

  // 데이터 수집 후 부모 뷰(food_list.dart)로 결과를 반환하며 pop 실행
  void _submit() {
    Navigator.pop(context, {
      'userType': selectedUserType,
      'preferenceText': preferenceController.text.trim(),
      'tasteLevels': tasteLevels,
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.black, size: 28),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text(
          '취향',
          style: TextStyle(color: Colors.black, fontWeight: FontWeight.bold),
        ),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // 1. 사용자 유형 섹션
                    Row(
                      children: [
                        const Text(
                          '사용자 유형',
                          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '(단일)',
                          style: TextStyle(color: Colors.grey[600], fontSize: 13),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),

                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: userTypes.map((type) {
                        final isSelected = selectedUserType == type['key'];
                        return Expanded(
                          child: GestureDetector(
                            onTap: () {
                              setState(() {
                                // 단일 선택 토글 처리: 동일 아이템 재클릭 시 선택 해제 처리
                                if (isSelected) {
                                  selectedUserType = '';
                                } else {
                                  selectedUserType = type['key']!;
                                }
                              });
                            },
                            child: Container(
                              margin: const EdgeInsets.symmetric(horizontal: 4),
                              padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
                              decoration: BoxDecoration(
                                color: isSelected ? Colors.grey[300] : Colors.grey[100],
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: isSelected ? Colors.grey[600]! : Colors.transparent,
                                  width: 2,
                                ),
                              ),
                              child: Column(
                                children: [
                                  Icon(
                                    type['icon'] as IconData,
                                    size: 40,
                                    color: isSelected ? Colors.black87 : Colors.black,
                                  ),
                                  const SizedBox(height: 12),
                                  Text(
                                    type['label']!,
                                    style: TextStyle(
                                      fontSize: 16,
                                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                                      color: Colors.black,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    type['sub']!,
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: isSelected ? Colors.black87 : Colors.grey[600],
                                      height: 1.3,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),

                    Divider(
                      height: 60,
                      thickness: 1,
                      color: Colors.grey[200],
                    ),

                    // 2. 자연어 입력 섹션
                    const Text(
                      '어떤 음식을 먹고 싶나요?',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: preferenceController,
                      maxLines: 3,
                      decoration: InputDecoration(
                        hintText: '예: 칼칼하고 감칠맛 있는 국물요리',
                        hintStyle: TextStyle(color: Colors.grey[400], fontSize: 14),
                        filled: true,
                        fillColor: Colors.white,
                        contentPadding: const EdgeInsets.all(16),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide(color: Colors.grey[300]!),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: Color(0xFF64B5F6), width: 1.5),
                        ),
                      ),
                    ),

                    Divider(
                      height: 60,
                      thickness: 1,
                      color: Colors.grey[200],
                    ),

                    // 3. 맛 조절 대제목 섹션
                    const Text(
                      '맛 조절',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 16),

                    // 4. 맛 조절 슬라이더 리스트 섹션 (테두리 조절)
                    ...tasteCategories.map((taste) {
                      final String key = taste['key']!;
                      final int currentLevel = tasteLevels[key] ?? 1;

                      return Container(
                        margin: const EdgeInsets.only(bottom: 14),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                        decoration: BoxDecoration(
                          color: Colors.white, // 상자 내부 배경색을 투명한 흰색으로 변경!
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: Colors.grey[300]!, // 테두리 선을 은은한 회색으로 유지
                            width: 1.2,
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Padding(
                              padding: const EdgeInsets.only(left: 4),
                              child: Text(
                                taste['label']!,
                                style: const TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.black87,
                                ),
                              ),
                            ),
                            const SizedBox(height: 4),
                            SliderTheme(
                              data: SliderTheme.of(context).copyWith(
                                activeTrackColor: const Color(0xFF64B5F6),
                                inactiveTrackColor: Colors.grey[200],
                                thumbColor: const Color(0xFF64B5F6),
                                trackHeight: 3.0,
                                thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 8),
                                overlayColor: const Color(0xFF64B5F6).withValues(alpha: 0.1),
                              ),
                              child: Column(
                                children: [
                                  Slider(
                                    value: currentLevel.toDouble(),
                                    min: 0,
                                    max: 2,
                                    divisions: 2, // 3단계(낮음/중간/높음) 이산적 값 선택을 위해 스텝 분할 제한
                                    onChanged: (value) {
                                      setState(() {
                                        tasteLevels[key] = value.toInt();
                                      });
                                    },
                                  ),
                                  const Padding(
                                    padding: EdgeInsets.symmetric(horizontal: 12),
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        Text('낮음', style: TextStyle(fontSize: 11, color: Colors.grey)),
                                        Text('중간', style: TextStyle(fontSize: 11, color: Colors.grey)),
                                        Text('높음', style: TextStyle(fontSize: 11, color: Colors.grey)),
                                      ],
                                    ),
                                  )
                                ],
                              ),
                            ),
                          ],
                        ),
                      );
                    }),
                  ],
                ),
              ),
            ),

            // 하단 고정 버튼
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
              child: SizedBox(
                width: double.infinity,
                height: 54,
                child: ElevatedButton(
                  onPressed: _submit,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF64B5F6),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    elevation: 0,
                  ),
                  child: const Text(
                    '이 취향으로 추천받기',
                    style: TextStyle(
                      color: Colors.black,
                      fontSize: 17,
                      fontWeight: FontWeight.bold,
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
}