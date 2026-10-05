// Unit tests for Mr.Sheven frontend models.
//
// 注：默认模板的计数器 widget 测试依赖不存在的 MyApp，且 ScanScreen 依赖
// 摄像头（widget 测试环境无法初始化），故这里只测纯 Dart 的响应模型解析。

import 'package:flutter_test/flutter_test.dart';
import 'package:mr_sheven/models/scan_result.dart';

void main() {
  group('ScanResult.fromJson', () {
    test('parses HIT_REVIEW envelope with EXACT match', () {
      final result = ScanResult.fromJson({
        'status': 'HIT_REVIEW',
        'match_level': 'EXACT',
        'wine': {
          'id': 34,
          'name': '奥兰小红帽珍藏',
          'brand': '奥兰',
        },
        'reviews': [
          {'id': 1, 'score_raw': '88', 'verdict': '好喝不贵'},
        ],
        'ocr_fields': {'product_name': '奥兰小红帽珍藏干红葡萄酒'},
        'reason': '同一款酒',
      });

      expect(result.hasReview, isTrue);
      expect(result.matchLevel, 'EXACT');
      expect(result.isSeries, isFalse);
      expect(result.wine?.name, '奥兰小红帽珍藏');
      expect(result.reviews, hasLength(1));
      expect(result.ocrProductName, '奥兰小红帽珍藏干红葡萄酒');
    });

    test('SERIES hit is flagged as reference-only', () {
      final result = ScanResult.fromJson({
        'status': 'HIT_REVIEW',
        'match_level': 'SERIES',
        'wine': {'id': 34, 'name': '奥兰小红帽珍藏', 'brand': '奥兰'},
        'reviews': [],
        'ocr_fields': {'product_name': '奥兰小红帽橡木桶干红葡萄酒（五号）'},
        'reason': '同系列不同款',
      });

      expect(result.isSeries, isTrue);
      expect(result.ocrProductName, '奥兰小红帽橡木桶干红葡萄酒（五号）');
    });

    test('NOT_FOUND with fallback candidates', () {
      final result = ScanResult.fromJson({
        'status': 'NOT_FOUND',
        'match_level': 'NONE',
        'fallback': [
          {'spu_id': 34, 'name': '奥兰小红帽珍藏', 'brand': '奥兰', 'score': 55.0},
        ],
        'reason': '无候选酒款',
      });

      expect(result.isNotFound, isTrue);
      expect(result.fallback, hasLength(1));
      expect(result.fallback.first.name, '奥兰小红帽珍藏');
    });
  });
}
