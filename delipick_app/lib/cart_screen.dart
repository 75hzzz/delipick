import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'models/cart.dart';

class CartScreen extends StatelessWidget {
  const CartScreen({super.key});

  static const Color _delipickBlue = Color(0xFF64B5F6);
  static final _fmt = NumberFormat('#,###');

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: _delipickBlue,
        foregroundColor: Colors.black,
        elevation: 0,
        title: const Text(
          '장바구니',
          style: TextStyle(fontWeight: FontWeight.bold, color: Colors.black),
        ),
        actions: [
          ListenableBuilder(
            listenable: cartModel,
            builder: (context, _) {
              if (cartModel.items.isEmpty) return const SizedBox.shrink();
              return TextButton(
                onPressed: () {
                  showDialog(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title: const Text('장바구니 비우기'),
                      content: const Text('담긴 항목을 모두 삭제할까요?'),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(ctx),
                          child: const Text('취소'),
                        ),
                        TextButton(
                          onPressed: () {
                            cartModel.clear();
                            Navigator.pop(ctx);
                          },
                          child: const Text('비우기', style: TextStyle(color: Colors.red)),
                        ),
                      ],
                    ),
                  );
                },
                child: const Text('전체 삭제', style: TextStyle(color: Colors.black87)),
              );
            },
          ),
        ],
      ),
      body: ListenableBuilder(
        listenable: cartModel,
        builder: (context, _) {
          if (cartModel.items.isEmpty) {
            return const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.shopping_cart_outlined, size: 72, color: Colors.grey),
                  SizedBox(height: 16),
                  Text(
                    '장바구니가 비어 있습니다',
                    style: TextStyle(fontSize: 16, color: Colors.grey),
                  ),
                ],
              ),
            );
          }

          return ListView.separated(
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
            itemCount: cartModel.items.length,
            separatorBuilder: (context, index) => const Divider(height: 1),
            itemBuilder: (context, index) {
              final cartItem = cartModel.items[index];
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    // 이미지
                    Container(
                      width: 64,
                      height: 64,
                      decoration: BoxDecoration(
                        color: Colors.grey[300],
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: (cartItem.imageUrl == null || cartItem.imageUrl!.isEmpty)
                            ? const Icon(Icons.fastfood, color: Colors.white)
                            : Image.network(
                                cartItem.imageUrl!,
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) =>
                                    const Icon(Icons.fastfood, color: Colors.white),
                              ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    // 이름 + 레스토랑 + 단가
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            cartItem.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                                fontSize: 15, fontWeight: FontWeight.bold),
                          ),
                          if ((cartModel.restaurantName ?? '').isNotEmpty)
                            Text(
                              cartModel.restaurantName!,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  fontSize: 12, color: Colors.grey),
                            ),
                          const SizedBox(height: 4),
                          Text(
                            cartItem.price == 0
                                ? '-'
                                : '${_fmt.format(cartItem.price)}원',
                            style: const TextStyle(
                                fontSize: 13, color: Colors.black87),
                          ),
                        ],
                      ),
                    ),
                    // 수량 스테퍼 + 삭제
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        // 삭제 버튼
                        GestureDetector(
                          onTap: () => cartModel.removeItem(cartItem),
                          child: const Icon(Icons.close, size: 18, color: Colors.grey),
                        ),
                        const SizedBox(height: 6),
                        // 수량 조절
                        Row(
                          children: [
                            _stepperButton(
                              icon: Icons.remove,
                              onTap: () => cartModel.decrement(cartItem),
                            ),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 10),
                              child: Text(
                                '${cartItem.quantity}',
                                style: const TextStyle(
                                    fontSize: 15, fontWeight: FontWeight.bold),
                              ),
                            ),
                            _stepperButton(
                              icon: Icons.add,
                              onTap: () => cartModel.increment(cartItem),
                            ),
                          ],
                        ),
                        // 소계
                        const SizedBox(height: 4),
                        Text(
                          cartItem.price == 0
                              ? ''
                              : '${_fmt.format(cartItem.price * cartItem.quantity)}원',
                          style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                              color: Colors.black),
                        ),
                      ],
                    ),
                  ],
                ),
              );
            },
          );
        },
      ),
      // 하단 합계 + 주문하기
      bottomNavigationBar: ListenableBuilder(
        listenable: cartModel,
        builder: (context, _) {
          if (cartModel.items.isEmpty) return const SizedBox.shrink();
          return Container(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
            decoration: const BoxDecoration(
              color: Colors.white,
              boxShadow: [
                BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, -2)),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      '총 ${cartModel.totalCount}개',
                      style: const TextStyle(fontSize: 14, color: Colors.grey),
                    ),
                    Text(
                      '합계 ${_fmt.format(cartModel.totalPrice)}원',
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                // 예상 배달 시간
                if (cartModel.deliveryTime > 0)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.fromLTRB(10, 8, 12, 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE3F2FD),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.access_time, size: 16, color: Colors.black54),
                        const SizedBox(width: 6),
                        Text(
                          '예상 배달 시간: ${cartModel.deliveryTime}분',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Colors.black,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  height: 50,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: _delipickBlue,
                      foregroundColor: Colors.black,
                      elevation: 0,
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8)),
                    ),
                    onPressed: () => _showOrderCompleteDialog(context),
                    child: Text(
                      '주문하기 (${_fmt.format(cartModel.totalPrice)}원)',
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  void _showOrderCompleteDialog(BuildContext context) {
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          cartModel.clear();
          Navigator.of(ctx).pop();
          Navigator.of(context).popUntil((route) => route.isFirst);
        },
        child: Dialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 72,
                  height: 72,
                  decoration: const BoxDecoration(
                    color: Color(0xFF64B5F6),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.check, color: Colors.white, size: 44),
                ),
                const SizedBox(height: 20),
                const Text(
                  '주문이 완료되었습니다!',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 10),
                const Text(
                  '화면을 누르면 메인으로 돌아갑니다.',
                  style: TextStyle(fontSize: 13, color: Colors.grey),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _stepperButton({required IconData icon, required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 28,
        height: 28,
        decoration: BoxDecoration(
          border: Border.all(color: Colors.grey[300]!),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Icon(icon, size: 16, color: Colors.black87),
      ),
    );
  }
}
