class Restaurant {
  final String name;
  final String mainMenu;
  final int price;
  final int deliveryTime;
  final double score;

  Restaurant({
    required this.name,
    required this.mainMenu,
    required this.price,
    required this.deliveryTime,
    required this.score,
  });

  factory Restaurant.fromJson(Map<String, dynamic> json) {
    return Restaurant(
      name: json['name'] ?? '이름 없음',
      mainMenu: json['main_menu'] ?? '메뉴 정보 없음',
      price: json['main_menu_price'] ?? 0,
      deliveryTime: json['delivery_time'] ?? 0,
      score: (json['final_score'] as num).toDouble(),
    );
  }
}