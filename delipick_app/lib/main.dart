import 'package:flutter/material.dart';
import 'food_list.dart';

void main() {
  runApp(const DelipickApp());
}

class DelipickApp extends StatelessWidget {
  const DelipickApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'delipick',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        primarySwatch: Colors.blue,
        scaffoldBackgroundColor: Colors.white,
        sliderTheme: const SliderThemeData(
          showValueIndicator: ShowValueIndicator.onDrag,
        ),
      ),
      home: const FoodListScreen(),
    );
  }
}
