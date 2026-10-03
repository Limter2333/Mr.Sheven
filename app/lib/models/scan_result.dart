import 'package:flutter/material.dart';

/// Scan result model matching server API response.
class ScanResult {
  final String status; // HIT_REVIEW / HIT_NO_REVIEW / NOT_WINE / NOT_FOUND
  final WineInfo? wine;
  final List<ReviewData> reviews;
  final List<FallbackItem> fallback;

  ScanResult({
    required this.status,
    this.wine,
    this.reviews = const [],
    this.fallback = const [],
  });

  factory ScanResult.fromJson(Map<String, dynamic> json) {
    return ScanResult(
      status: json['status'] ?? 'NOT_FOUND',
      wine: json['wine'] != null ? WineInfo.fromJson(json['wine']) : null,
      reviews: (json['reviews'] as List<dynamic>?)
              ?.map((r) => ReviewData.fromJson(r))
              .toList() ??
          [],
      fallback: (json['fallback'] as List<dynamic>?)
              ?.map((f) => FallbackItem.fromJson(f))
              .toList() ??
          [],
    );
  }

  bool get hasReview => status == 'HIT_REVIEW';
  bool get isNotFound => status == 'NOT_FOUND';
  bool get isNotWine => status == 'NOT_WINE';
  bool get hasNoReview => status == 'HIT_NO_REVIEW';
}

class WineInfo {
  final int? id;
  final String name;
  final String? brand;
  final String? category;
  final String? country;
  final String? region;
  final double? abv;
  final int? volumeMl;

  WineInfo({
    this.id,
    required this.name,
    this.brand,
    this.category,
    this.country,
    this.region,
    this.abv,
    this.volumeMl,
  });

  factory WineInfo.fromJson(Map<String, dynamic> json) {
    return WineInfo(
      id: json['id'],
      name: json['name'] ?? '',
      brand: json['brand'],
      category: json['category'],
      country: json['country'],
      region: json['region'],
      abv: json['abv']?.toDouble(),
      volumeMl: json['volume_ml'],
    );
  }
}

class ReviewData {
  final int? id;
  final int mid;
  final String? scoreRaw;
  final String? scoreType;
  final String? verdict; // recommend / neutral / avoid
  final List<String> flavorTags;
  final int? recommendIndex;
  final String? quote;
  final int? tsStart;
  final int? tsEnd;
  final String? scoreTrend;
  final String? trendReason;
  final double? confidence;
  final String? createdAt;

  ReviewData({
    this.id,
    required this.mid,
    this.scoreRaw,
    this.scoreType,
    this.verdict,
    this.flavorTags = const [],
    this.recommendIndex,
    this.quote,
    this.tsStart,
    this.tsEnd,
    this.scoreTrend,
    this.trendReason,
    this.confidence,
    this.createdAt,
  });

  factory ReviewData.fromJson(Map<String, dynamic> json) {
    return ReviewData(
      id: json['id'],
      mid: json['mid'] ?? 0,
      scoreRaw: json['score_raw'],
      scoreType: json['score_type'],
      verdict: json['verdict'],
      flavorTags: (json['flavor_tags'] as List<dynamic>?)
              ?.map((t) => t.toString())
              .toList() ??
          [],
      recommendIndex: json['recommend_index'],
      quote: json['quote'],
      tsStart: json['ts_start'],
      tsEnd: json['ts_end'],
      scoreTrend: json['score_trend'],
      trendReason: json['trend_reason'],
      confidence: json['confidence']?.toDouble(),
      createdAt: json['created_at'],
    );
  }

  String get verdictLabel {
    switch (verdict) {
      case 'recommend':
        return '推荐';
      case 'neutral':
        return '中性';
      case 'avoid':
        return '避雷';
      default:
        return '未知';
    }
  }

  Color get verdictColor {
    switch (verdict) {
      case 'recommend':
        return const Color(0xFF4CAF50);
      case 'neutral':
        return const Color(0xFFFF9800);
      case 'avoid':
        return const Color(0xFFF44336);
      default:
        return const Color(0xFF9E9E9E);
    }
  }

  String get scoreTrendLabel {
    switch (scoreTrend) {
      case 'UP':
        return '↑ 升分';
      case 'DOWN':
        return '↓ 降分';
      case 'SAME':
        return '→ 持平';
      default:
        return '';
    }
  }
}

class FallbackItem {
  final int spuId;
  final String name;

  FallbackItem({required this.spuId, required this.name});

  factory FallbackItem.fromJson(Map<String, dynamic> json) {
    return FallbackItem(
      spuId: json['spu_id'] ?? 0,
      name: json['name'] ?? '',
    );
  }
}