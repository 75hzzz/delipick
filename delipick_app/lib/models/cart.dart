import 'package:flutter/foundation.dart';
import 'restaurant.dart';

class CartItem {
  final int itemKey; // menu.id
  final String name;
  final int price;
  final String? imageUrl;
  int quantity;

  CartItem({
    required this.itemKey,
    required this.name,
    required this.price,
    this.imageUrl,
    this.quantity = 1,
  });

  factory CartItem.fromMenu(MenuItem menu) {
    return CartItem(
      itemKey: menu.id,
      name: menu.menuName,
      price: menu.price ?? 0,
      imageUrl: menu.imageUrl,
    );
  }
}

class CartModel extends ChangeNotifier {
  final List<CartItem> _items = [];

  // 현재 담긴 식당 정보
  int? restaurantId;
  String? restaurantName;
  int deliveryTime = 0; // 분

  List<CartItem> get items => List.unmodifiable(_items);

  int get totalCount => _items.fold(0, (sum, e) => sum + e.quantity);

  int get totalPrice => _items.fold(0, (sum, e) => sum + e.price * e.quantity);

  /// 담기 시도.
  /// 같은 식당이거나 비어 있으면 추가 후 true 반환.
  /// 다른 식당이면 추가하지 않고 false 반환 (UI에서 교체 확인 필요).
  bool tryAddMenu(
    MenuItem menu, {
    required int restaurantId,
    required String restaurantName,
    required int deliveryTime,
  }) {
    if (_items.isNotEmpty && this.restaurantId != restaurantId) {
      return false;
    }
    _addMenuInternal(menu, restaurantId: restaurantId, restaurantName: restaurantName, deliveryTime: deliveryTime);
    return true;
  }

  /// 장바구니를 비우고 새 식당 메뉴로 교체.
  void replaceWithMenu(
    MenuItem menu, {
    required int restaurantId,
    required String restaurantName,
    required int deliveryTime,
  }) {
    _items.clear();
    _addMenuInternal(menu, restaurantId: restaurantId, restaurantName: restaurantName, deliveryTime: deliveryTime);
  }

  void _addMenuInternal(
    MenuItem menu, {
    required int restaurantId,
    required String restaurantName,
    required int deliveryTime,
  }) {
    this.restaurantId = restaurantId;
    this.restaurantName = restaurantName;
    this.deliveryTime = deliveryTime;

    final existing = _items.where((e) => e.itemKey == menu.id).firstOrNull;
    if (existing != null) {
      existing.quantity += 1;
    } else {
      _items.add(CartItem.fromMenu(menu));
    }
    notifyListeners();
  }

  void increment(CartItem cartItem) {
    final target = _items.where((e) => e.itemKey == cartItem.itemKey).firstOrNull;
    if (target != null) {
      target.quantity += 1;
      notifyListeners();
    }
  }

  void decrement(CartItem cartItem) {
    final target = _items.where((e) => e.itemKey == cartItem.itemKey).firstOrNull;
    if (target != null) {
      if (target.quantity > 1) {
        target.quantity -= 1;
      } else {
        _items.remove(target);
      }
      notifyListeners();
    }
  }

  void removeItem(CartItem cartItem) {
    _items.removeWhere((e) => e.itemKey == cartItem.itemKey);
    if (_items.isEmpty) _resetMeta();
    notifyListeners();
  }

  void clear() {
    _items.clear();
    _resetMeta();
    notifyListeners();
  }

  void _resetMeta() {
    restaurantId = null;
    restaurantName = null;
    deliveryTime = 0;
  }
}

/// 전역 싱글톤 — 어느 파일에서든 import해서 사용
final cartModel = CartModel();
