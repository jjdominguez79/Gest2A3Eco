import 'package:flutter/material.dart';

import 'root_gate.dart';

class GestinemApp extends StatelessWidget {
  const GestinemApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GestinemAppFull',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF005F73),
          brightness: Brightness.light,
        ),
        scaffoldBackgroundColor: const Color(0xFFF5F7FA),
        useMaterial3: true,
      ),
      home: const RootGate(),
    );
  }
}
