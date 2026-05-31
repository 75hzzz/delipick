class RestaurantItem {
  final int? menuId;
  final int id;
  final String name;
  final String? restaurantName;
  final int? categoryId;
  final String? categoryName;
  final String? address;
  final double rating;
  final String? mainMenu;
  final int? mainMenuPrice;
  final String? imageUrl;
  final int? prepTime;
  final int? deliveryTime;
  final double estimatedTotalTime;
  final double queuingWait;
  final bool isPeakTime;

  final double deliveryScore;
  final double priceScore;
  final double restaurantReviewScore;
  final double preferenceScore;
  final double finalScore;
  final String? recommendationReason;

  const RestaurantItem({
    required this.menuId,
    required this.id,
    required this.name,
    required this.restaurantName,
    required this.categoryId,
    required this.categoryName,
    required this.address,
    required this.rating,
    required this.mainMenu,
    required this.mainMenuPrice,
    required this.imageUrl,
    required this.prepTime,
    required this.deliveryTime,
    required this.estimatedTotalTime,
    required this.queuingWait,
    required this.isPeakTime,
    required this.deliveryScore,
    required this.priceScore,
    required this.restaurantReviewScore,
    required this.preferenceScore,
    required this.finalScore,
    required this.recommendationReason,
  });

  factory RestaurantItem.fromJson(Map<String, dynamic> json) {
    return RestaurantItem(
      menuId: (json['menu_id'] as num?)?.toInt(),
      id: (json['id'] as num).toInt(),
      name: json['name'] as String? ?? '',
      restaurantName: json['restaurant_name'] as String?,
      categoryId: (json['category_id'] as num?)?.toInt(),
      categoryName: json['category_name'] as String?,
      address: json['address'] as String?,
      rating: (json['rating'] as num?)?.toDouble() ?? 0,
      mainMenu: json['main_menu'] as String?,
      mainMenuPrice: (json['main_menu_price'] as num?)?.toInt(),
      imageUrl: json['image_url'] as String?,
      prepTime: (json['prep_time'] as num?)?.toInt(),
      deliveryTime: (json['delivery_time'] as num?)?.toInt(),
      estimatedTotalTime: (json['estimated_total_time'] as num?)?.toDouble() ?? 0,
      queuingWait: (json['queuing_wait'] as num?)?.toDouble() ?? 0,
      isPeakTime: json['is_peak_time'] as bool? ?? false,
      deliveryScore: (json['delivery_score'] as num?)?.toDouble() ?? 0,
      priceScore: (json['price_score'] as num?)?.toDouble() ?? 0,
      restaurantReviewScore: (json['restaurant_review_score'] as num?)?.toDouble() ?? 0.5,
      preferenceScore: (json['preference_score'] as num?)?.toDouble() ?? 0.5,
      finalScore: (json['final_score'] as num?)?.toDouble() ?? 0,
      recommendationReason: json['recommendation_reason'] as String?,
    );
  }
}

class RecommendationData {
  final String mode;
  final String? userType;
  final String preferenceText;
  final List<RestaurantItem> items;

  const RecommendationData({
    required this.mode,
    required this.userType,
    required this.preferenceText,
    required this.items,
  });

  factory RecommendationData.fromJson(Map<String, dynamic> json) {
    final List<dynamic> rawItems = json['items'] as List<dynamic>? ?? const [];
    return RecommendationData(
      mode: json['mode'] as String? ?? 'default_delivery',
      userType: json['user_type'] as String?,
      preferenceText: json['preference_text'] as String? ?? '',
      items: rawItems
          .whereType<Map<String, dynamic>>()
          .map(RestaurantItem.fromJson)
          .toList(),
    );
  }
}

class CategoryItem {
  final int id;
  final String name;
  final String imageAsset;

  const CategoryItem({
    required this.id,
    required this.name,
    required this.imageAsset,
  });

  factory CategoryItem.fromJson(Map<String, dynamic> json, String imageAsset) {
    return CategoryItem(
      id: (json['category_id'] as num).toInt(),
      name: json['category_name'] as String? ?? '',
      imageAsset: imageAsset,
    );
  }
}
