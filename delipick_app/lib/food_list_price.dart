import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

class PriceRangeSheet extends StatefulWidget {
  final RangeValues initialRange;

  const PriceRangeSheet({super.key, required this.initialRange});

  @override
  State<PriceRangeSheet> createState() => _PriceRangeSheetState();
}

class _PriceRangeSheetState extends State<PriceRangeSheet> {
  late RangeValues _currentRange;
  final NumberFormat _formatter = NumberFormat('#,###');

  @override
  void initState() {
    super.initState();
    _currentRange = widget.initialRange;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.45,
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
          const Text('가격범위', style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
          const Divider(indent: 20, endIndent: 20),
          const Spacer(),

          // 가격 표시 박스 영역
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 30),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _buildPriceBox(_currentRange.start),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 10),
                  child: Text('~', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                ),
                _buildPriceBox(_currentRange.end),
              ],
            ),
          ),
          const SizedBox(height: 30),

          // 슬라이더 영역
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: SliderTheme(
              data: SliderTheme.of(context).copyWith(
                activeTrackColor: const Color(0xFF64B5F6),
                inactiveTrackColor: Colors.grey[200],
                thumbColor: Colors.white,
                overlayColor: const Color(0xFF64B5F6).withValues(alpha: 0.2),
                rangeThumbShape: const RoundRangeSliderThumbShape(
                  enabledThumbRadius: 12,
                  elevation: 5,
                ),
              ),
              child: RangeSlider(
                values: _currentRange,
                min: 2000,
                max: 100000,
                divisions: 98, // (100,000 - 2,000) / 1,000 단위
                onChanged: (RangeValues values) {
                  setState(() {
                    _currentRange = values;
                  });
                },
              ),
            ),
          ),
          const Spacer(),

          // 확인 버튼
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 15),
              child: SizedBox(
                width: double.infinity,
                height: 55,
                child: ElevatedButton(
                  onPressed: () => Navigator.pop(context, _currentRange),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF64B5F6),
                    elevation: 0,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  child: const Text('확인', style: TextStyle(fontSize: 18, color: Colors.black, fontWeight: FontWeight.bold)),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPriceBox(double value) {
    // 초기값이거나 변경되지 않았을 때의 색상 처리를 위한 로직
    bool isDefault = (value == 2000 || value == 100000);

    return Container(
      width: 130,
      height: 45,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        border: Border.all(color: Colors.grey[300]!),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        '${_formatter.format(value.toInt())} 원',
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w500,
          color: isDefault ? Colors.grey[400] : Colors.black, // 설정 안했을 때 회색 처리
        ),
      ),
    );
  }
}