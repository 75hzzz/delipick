import 'package:flutter/material.dart';

class TastePreferenceScreen extends StatefulWidget {
  final String initialUserType;
  final String initialPreferenceText;

  const TastePreferenceScreen({
    super.key,
    required this.initialUserType,
    required this.initialPreferenceText,
  });

  @override
  State<TastePreferenceScreen> createState() => _TastePreferenceScreenState();
}

class _TastePreferenceScreenState extends State<TastePreferenceScreen> {
  late String selectedUserType;
  late TextEditingController preferenceController;

  final List<Map<String, String>> userTypes = const [
    {'key': 'convenience', 'label': '편의형'},
    {'key': 'gourmet', 'label': '미식형'},
    {'key': 'budget', 'label': '경제형'},
  ];

  @override
  void initState() {
    super.initState();
    selectedUserType = widget.initialUserType;
    preferenceController = TextEditingController(text: widget.initialPreferenceText);
  }

  @override
  void dispose() {
    preferenceController.dispose();
    super.dispose();
  }

  void _submit() {
    Navigator.pop(context, {
      'userType': selectedUserType,
      'preferenceText': preferenceController.text.trim(),
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
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
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '사용자 유형',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 10),
            ...userTypes.map(
              (type) => CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                controlAffinity: ListTileControlAffinity.leading,
                title: Text(type['label']!),
                value: selectedUserType == type['key'],
                onChanged: (_) {
                  setState(() {
                    if (selectedUserType == type['key']) {
                      selectedUserType = '';
                    } else {
                      selectedUserType = type['key']!;
                    }
                  });
                },
              ),
            ),
            const SizedBox(height: 14),
            const Text(
              '자연어 입력',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: preferenceController,
              maxLines: 4,
              decoration: InputDecoration(
                hintText: '예: 칼칼하고 감칠맛 있는 국물요리 먹고 싶어요',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Color(0xFF64B5F6), width: 1.4),
                ),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '유형은 하나만 선택하거나 비워둘 수 있습니다.',
              style: TextStyle(color: Colors.grey, fontSize: 13),
            ),
            const Spacer(),
            SafeArea(
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
