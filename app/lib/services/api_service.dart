import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:mr_sheven/models/scan_result.dart';

/// API service for communicating with Mr.Sheven backend.
class ApiService extends ChangeNotifier {
  // TODO: Make configurable via settings
  // static const String _baseUrl = 'http://10.0.2.2:8000'; // Android emulator
  static const String _baseUrl = 'http://localhost:8000'; // Web / iOS simulator / Desktop

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

  /// Scan a wine back-label image (OCR 主链路，裁决 C12).
  ///
  /// [imageBytes] 上传酒标图片；[text] 为调试透传（跳过 OCR）；[barcode] 可选，
  /// 识别成功后服务端回写 barcode↔SPU 绑定（自增长）。
  Future<ScanResult?> scanLabel({
    Uint8List? imageBytes,
    String? text,
    String? barcode,
  }) async {
    if (imageBytes == null && (text == null || text.trim().isEmpty)) {
      _error = '请提供酒标图片或文字';
      notifyListeners();
      return null;
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final uri = Uri.parse('$_baseUrl/api/v1/scan-label');
      final request = http.MultipartRequest('POST', uri);

      if (imageBytes != null) {
        request.files.add(http.MultipartFile.fromBytes(
          'image',
          imageBytes,
          filename: 'label.jpg',
          // Web 端不显式指定会变成 application/octet-stream，服务端无法识别
          contentType: MediaType.parse(_sniffImageMime(imageBytes)),
        ));
      }
      if (text != null && text.trim().isNotEmpty) {
        request.fields['text'] = text.trim();
      }
      if (barcode != null && barcode.trim().isNotEmpty) {
        request.fields['barcode'] = barcode.trim();
      }

      final streamed = await request.send().timeout(
        const Duration(seconds: 60),
      );
      final response = await http.Response.fromStream(streamed);

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        _lastResult = ScanResult.fromJson(data);
        _isLoading = false;
        notifyListeners();
        return _lastResult;
      } else if (response.statusCode == 429) {
        _error = '请求太频繁，请稍后再试';
      } else {
        // 服务端错误信息（如 OCR 未配置/图片超限）直接透出
        try {
          final data = json.decode(response.body);
          _error = data['error'] ?? '识别失败 (${response.statusCode})';
        } catch (_) {
          _error = '识别失败 (${response.statusCode})';
        }
      }
    } catch (e) {
      _error = '网络连接失败，请检查网络';
      debugPrint('Label scan error: $e');
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

/// 按文件头嗅探图片 MIME（Web 端 picker 常丢 Content-Type），默认按 JPEG。
String _sniffImageMime(Uint8List bytes) {
  if (bytes.length >= 8 &&
      bytes[0] == 0x89 &&
      bytes[1] == 0x50 &&
      bytes[2] == 0x4E &&
      bytes[3] == 0x47) {
    return 'image/png';
  }
  if (bytes.length >= 12 &&
      bytes[0] == 0x52 &&
      bytes[1] == 0x49 &&
      bytes[2] == 0x46 &&
      bytes[3] == 0x46 &&
      bytes[8] == 0x57 &&
      bytes[9] == 0x45 &&
      bytes[10] == 0x42 &&
      bytes[11] == 0x50) {
    return 'image/webp';
  }
  return 'image/jpeg';
}