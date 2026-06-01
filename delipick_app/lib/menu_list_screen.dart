import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'cart_screen.dart';
import 'models/cart.dart';
import 'models/restaurant.dart';
import 'services/api_service.dart';

class MenuListScreen extends StatefulWidget {
  final int restaurantId;
  final String restaurantName;
  final int deliveryTime;

  const MenuListScreen({
    super.key,
    required this.restaurantId,
    required this.restaurantName,
    required this.deliveryTime,
  });

  @override
  State<MenuListScreen> createState() => _MenuListScreenState();
}

class _MenuListScreenState extends State<MenuListScreen> {
  static const Color _delipickBlue = Color(0xFF64B5F6);
  static final _fmt = NumberFormat('#,###');

  final DelipickApiService _apiService = DelipickApiService();

  bool _isLoading = true;
  String? _errorMessage;
  List<MenuItem> _menus = [];

  @override
  void initState() {
    super.initState();
    _fetchMenus();
  }

  @override
  void dispose() {
    _apiService.dispose();
    super.dispose();
  }

  Future<void> _fetchMenus() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final menus = await _apiService.fetchMenus(widget.restaurantId);
      if (mounted) {
        setState(() {
          _menus = menus;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _handleAddToCart(MenuItem menu) async {
    final added = cartModel.tryAddMenu(
      menu,
      restaurantId: widget.restaurantId,
      restaurantName: widget.restaurantName,
      deliveryTime: widget.deliveryTime,
    );

    if (added) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).clearSnackBars();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${menu.menuName}을(를) 장바구니에 담았습니다.'),
          duration: const Duration(seconds: 1),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } else {
      if (!mounted) return;
      final confirm = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('다른 가게 메뉴가 있습니다'),
          content: Text(
            '장바구니에 "${cartModel.restaurantName}" 메뉴가 담겨 있습니다.\n비우고 "${widget.restaurantName}" 메뉴를 담을까요?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('취소'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('비우고 담기', style: TextStyle(color: Colors.red)),
            ),
          ],
        ),
      );

      if (confirm == true) {
        cartModel.replaceWithMenu(
          menu,
          restaurantId: widget.restaurantId,
          restaurantName: widget.restaurantName,
          deliveryTime: widget.deliveryTime,
        );
        if (!mounted) return;
        ScaffoldMessenger.of(context).clearSnackBars();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${menu.menuName}을(를) 장바구니에 담았습니다.'),
            duration: const Duration(seconds: 1),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: _delipickBlue,
        foregroundColor: Colors.black,
        elevation: 0,
        title: Text(
          widget.restaurantName,
          style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.black),
        ),
        actions: [
          // 헤더 장바구니 아이콘 (뱃지 포함)
          ListenableBuilder(
            listenable: cartModel,
            builder: (context, child) {
              final count = cartModel.totalCount;
              return Stack(
                clipBehavior: Clip.none,
                children: [
                  IconButton(
                    icon: const Icon(
                      Icons.shopping_cart_outlined,
                      color: Colors.black,
                      size: 26,
                    ),
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (context) => const CartScreen()),
                      );
                    },
                  ),
                  if (count > 0)
                    Positioned(
                      top: 6,
                      right: 6,
                      child: Container(
                        width: 17,
                        height: 17,
                        decoration: const BoxDecoration(
                          color: Colors.red,
                          shape: BoxShape.circle,
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          count > 99 ? '99+' : '$count',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
        ],
      ),
      body: _buildBody(),
      bottomNavigationBar: ListenableBuilder(
        listenable: cartModel,
        builder: (context, child) {
          if (cartModel.items.isEmpty) return const SizedBox.shrink();
          return GestureDetector(
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const CartScreen()),
              );
            },
            child: Container(
              height: 64,
              color: _delipickBlue,
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Row(
                children: [
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '합계 ${_fmt.format(cartModel.totalPrice)}원',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: Colors.black,
                        ),
                      ),
                      Text(
                        '총 ${cartModel.totalCount}개',
                        style: const TextStyle(fontSize: 12, color: Colors.black87),
                      ),
                    ],
                  ),
                  const Spacer(),
                  Row(
                    children: const [
                      Icon(Icons.shopping_cart, color: Colors.black, size: 20),
                      SizedBox(width: 6),
                      Text(
                        '장바구니 보기',
                        style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.bold,
                          color: Colors.black,
                        ),
                      ),
                      SizedBox(width: 4),
                      Icon(Icons.chevron_right, color: Colors.black, size: 20),
                    ],
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_errorMessage != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: Colors.grey),
              const SizedBox(height: 12),
              Text(
                '메뉴를 불러오지 못했습니다.',
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              Text(
                _errorMessage!,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: _delipickBlue,
                  foregroundColor: Colors.black,
                ),
                onPressed: _fetchMenus,
                child: const Text('다시 시도'),
              ),
            ],
          ),
        ),
      );
    }

    if (_menus.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.restaurant_menu, size: 60, color: Colors.grey),
            SizedBox(height: 12),
            Text('등록된 메뉴가 없습니다.', style: TextStyle(fontSize: 16, color: Colors.grey)),
          ],
        ),
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      itemCount: _menus.length,
      separatorBuilder: (context, index) => const Divider(height: 1),
      itemBuilder: (context, index) => _buildMenuItem(_menus[index]),
    );
  }

  Widget _buildMenuItem(MenuItem menu) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          // 이미지
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              color: Colors.grey[300],
              borderRadius: BorderRadius.circular(8),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: (menu.imageUrl == null || menu.imageUrl!.isEmpty)
                  ? const Icon(Icons.fastfood, color: Colors.white, size: 36)
                  : Image.network(
                      menu.imageUrl!,
                      fit: BoxFit.cover,
                      errorBuilder: (context, error, stackTrace) =>
                          const Icon(Icons.fastfood, color: Colors.white, size: 36),
                    ),
            ),
          ),
          const SizedBox(width: 12),
          // 메뉴명 + 가격
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  menu.menuName,
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  menu.price == null ? '-' : '${_fmt.format(menu.price)}원',
                  style: const TextStyle(fontSize: 14, color: Colors.black87),
                ),
              ],
            ),
          ),
          // 담기 버튼
          SizedBox(
            height: 36,
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: _delipickBlue,
                foregroundColor: Colors.black,
                elevation: 0,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              icon: const Icon(Icons.add_shopping_cart, size: 16),
              label: const Text('담기', style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold)),
              onPressed: () => _handleAddToCart(menu),
            ),
          ),
        ],
      ),
    );
  }
}
