import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:mr_sheven/services/api_service.dart';
import 'package:mr_sheven/app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    ChangeNotifierProvider(
      create: (_) => ApiService(),
      child: const MrShevenApp(),
    ),
  );
}