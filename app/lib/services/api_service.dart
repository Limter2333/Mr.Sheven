import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:mr_sheven/models/scan_result.dart';

/// API service for communicating with Mr.Sheven backend.
class ApiService extends ChangeNotifier {
  // TODO: Make configurable via settings
  static const String _baseUrl = 'http://10.0.2.2:8000'; // Android emulator
  // static const String _baseUrl = 'http://localhost:8000'; // iOS simulator

  bool _isLoading = false;
  String? _error;
  ScanResult? _lastResult;

  bool get isLoading => _isLoading;
  String? get error => _error;
  ScanResult? get lastResult => _lastResult;

  /// Scan a barcode and get wine review results.
  Future<ScanResult?> scanBarcode(String barcode) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final uri = Uri.parse('$_baseUrl/api/v1/scan?barcode=$barcode');
      final response = await http.get(uri).timeout(
        const Duration(seconds: 10),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        _lastResult = ScanResult.fromJson(data);
        _isLoading = false;
        notifyListeners();
        return _lastResult;
      } else if (response.statusCode == 429) {
        _error = '请求太频繁，请稍后再试';
      } else {
        _error = '服务器错误 (${response.statusCode})';
      }
    } catch (e) {
      _error = '网络连接失败，请检查网络';
      debugPrint('API error: $e');
    }

    _isLoading = false;
    notifyListeners();
    return null;
  }

  /// Get SPU detail with reviews.
  Future<Map<String, dynamic>?> getSpuReviews(int spuId) async {
    try {
      final uri = Uri.parse('$_baseUrl/api/v1/spu/$spuId/reviews');
      final response = await http.get(uri).timeout(
        const Duration(seconds: 10),
      );

      if (response.statusCode == 200) {
        return json.decode(response.body);
      }
    } catch (e) {
      debugPrint('SPU detail error: $e');
    }
    return null;
  }

  /// Submit feedback (placeholder).
  Future<bool> submitFeedback({
    required String barcode,
    required String feedback,
    String? taste,
  }) async {
    // TODO: Implement feedback API endpoint
    debugPrint('Feedback submitted: $barcode - $feedback');
    return true;
  }

  void clearResult() {
    _lastResult = null;
    _error = null;
    notifyListeners();
  }
}