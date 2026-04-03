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
      title: 'DeliPick',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        primaryColor: const Color(0xFF64B5F6),
        scaffoldBackgroundColor: Colors.white,
      ),
      home: const FoodListScreen(),
    );
  }
}