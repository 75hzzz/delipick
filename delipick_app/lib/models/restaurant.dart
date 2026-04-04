class RestaurantItem {
  final int id;
  final String name;
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
  final int llmScore;
  final double finalScore;

  const RestaurantItem({
    required this.id,
    required this.name,
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
    required this.llmScore,
    required this.finalScore,
  });

  factory RestaurantItem.fromJson(Map<String, dynamic> json) {
    return RestaurantItem(
      id: (json['id'] as num).toInt(),
      name: json['name'] as String? ?? '',
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
      llmScore: (json['llm_score'] as num?)?.toInt() ?? 0,
      finalScore: (json['final_score'] as num?)?.toDouble() ?? 0,
    );
  }
}

class RecommendationData {
  final String weatherStatus;
  final double weatherTemp;
  final List<RestaurantItem> items;

  const RecommendationData({
    required this.weatherStatus,
    required this.weatherTemp,
    required this.items,
  });

  factory RecommendationData.fromJson(Map<String, dynamic> json) {
    final List<dynamic> rawItems = json['items'] as List<dynamic>? ?? const [];
    return RecommendationData(
      weatherStatus: json['weather_status'] as String? ?? '맑음',
      weatherTemp: (json['weather_temp'] as num?)?.toDouble() ?? 20,
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
