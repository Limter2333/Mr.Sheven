import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:mr_sheven/services/api_service.dart';
import 'package:mr_sheven/app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // 先读持久化的服务器地址（花生壳映射等），再启动 UI
  final api = ApiService();
  await api.init();
  runApp(
    ChangeNotifierProvider(
      create: (_) => api,
      child: const MrShevenApp(),
    ),
  );
}