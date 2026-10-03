import 'package:flutter/material.dart';
import 'package:mr_sheven/models/scan_result.dart';
import 'package:mr_sheven/screens/feedback_screen.dart';
import 'package:url_launcher/url_launcher.dart';

class ResultScreen extends StatelessWidget {
  final String barcode;
  final ScanResult result;

  const ResultScreen({
    super.key,
    required this.barcode,
    required this.result,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('扫描结果'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: switch (result.status) {
          'HIT_REVIEW' => _buildHitReview(context),
          'HIT_NO_REVIEW' => _buildHitNoReview(context),
          'NOT_WINE' => _buildNotWine(context),
          'NOT_FOUND' => _buildNotFound(context),
          _ => _buildNotFound(context),
        },
      ),
    );
  }

  /// 有评测 - 突出权威背书
  Widget _buildHitReview(BuildContext context) {
    final theme = Theme.of(context);
    final wine = result.wine!;
    final reviews = result.reviews;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Wine info card
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  wine.name,
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                if (wine.brand != null)
                  _infoRow('品牌', wine.brand!),
                if (wine.category != null)
                  _infoRow('品类', _categoryLabel(wine.category!)),
                if (wine.country != null)
                  _infoRow('产地', '${wine.country}${wine.region != null ? " · ${wine.region}" : ""}'),
                if (wine.abv != null)
                  _infoRow('酒精度', '${wine.abv}%'),
                if (wine.volumeMl != null)
                  _infoRow('容量', '${wine.volumeMl}ml'),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),

        // Reviews
        Text(
          '博主评测 (${reviews.length})',
          style: theme.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 8),
        ...reviews.map((review) => _buildReviewCard(context, review)),

        const SizedBox(height: 16),
        _buildFeedbackButton(context, barcode),
      ],
    );
  }

  Widget _buildReviewCard(BuildContext context, ReviewData review) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Score and verdict
            Row(
              children: [
                if (review.scoreRaw != null) ...[
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: _verdictBgColor(review.verdict),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '${review.scoreRaw}${review.scoreType == "pct100" ? "分" : ""}',
                      style: theme.textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                ],
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: _verdictColor(review.verdict).withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                    border: Border.all(
                      color: _verdictColor(review.verdict),
                    ),
                  ),
                  child: Text(
                    review.verdictLabel,
                    style: TextStyle(
                      color: _verdictColor(review.verdict),
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                const Spacer(),
                if (review.scoreTrend != null)
                  Text(
                    review.scoreTrendLabel,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: review.scoreTrend == 'UP'
                          ? Colors.green
                          : review.scoreTrend == 'DOWN'
                              ? Colors.red
                              : Colors.grey,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 12),

            // Quote
            if (review.quote != null && review.quote!.isNotEmpty)
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(8),
                  border: Border(
                    left: BorderSide(
                      color: theme.colorScheme.primary,
                      width: 3,
                    ),
                  ),
                ),
                child: Text(
                  '"${review.quote}"',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ),
            const SizedBox(height: 8),

            // Flavor tags
            if (review.flavorTags.isNotEmpty)
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: review.flavorTags
                    .map((tag) => Chip(
                          label: Text(tag, style: const TextStyle(fontSize: 12)),
                          padding: EdgeInsets.zero,
                          materialTapTargetSize:
                              MaterialTapTargetSize.shrinkWrap,
                        ))
                    .toList(),
              ),

            // Video link
            if (review.tsStart != null)
              TextButton.icon(
                onPressed: () {
                  // TODO: Open Bilibili video at timestamp
                  _showVideoLink(context, review);
                },
                icon: const Icon(Icons.play_circle_outline, size: 16),
                label: Text(
                  '跳转到 ${_formatTimestamp(review.tsStart!)}',
                  style: theme.textTheme.bodySmall,
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// 无评测 - 温情提示卡（裁决C3）
  Widget _buildHitNoReview(BuildContext context) {
    final theme = Theme.of(context);
    final wine = result.wine;

    return Column(
      children: [
        if (wine != null) ...[
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(wine.name, style: theme.textTheme.headlineSmall),
                  if (wine.brand != null) ...[
                    const SizedBox(height: 4),
                    Text(wine.brand!, style: theme.textTheme.bodyMedium),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
        ],

        // 温情提示卡
        Card(
          color: theme.colorScheme.surfaceContainerHighest,
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              children: [
                Icon(
                  Icons.info_outline,
                  size: 48,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                const SizedBox(height: 12),
                Text(
                  '暂无博主评测',
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '这款酒目前还没有被博主评测过哦。\n在酒圈里，没有口碑的酒往往意味着风险较高，建议您谨慎购买。',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 16),
                // 兜底推荐
                if (result.fallback.isNotEmpty) ...[
                  const Divider(),
                  const SizedBox(height: 8),
                  Text(
                    '您可以看看这几款同品类的酒：',
                    style: theme.textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 8),
                  ...result.fallback.map((item) => ListTile(
                        leading: const Icon(Icons.wine_bar),
                        title: Text(item.name),
                        dense: true,
                      )),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        _buildFeedbackButton(context, barcode),
      ],
    );
  }

  /// 非酒类
  Widget _buildNotWine(BuildContext context) {
    final theme = Theme.of(context);

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 60),
          Icon(
            Icons.local_bar,
            size: 64,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 16),
          Text(
            '扫描到的不是酒类商品哦',
            style: theme.textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(
            '请对准酒瓶上的条形码',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text('重新扫描'),
          ),
        ],
      ),
    );
  }

  /// 查无此酒
  Widget _buildNotFound(BuildContext context) {
    final theme = Theme.of(context);

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 60),
          Icon(
            Icons.search_off,
            size: 64,
            color: theme.colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: 16),
          Text(
            '未找到该商品信息',
            style: theme.textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          Text(
            '这可能是未收录的冷门酒或商品码已失效',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => FeedbackScreen(barcode: barcode),
                ),
              );
            },
            icon: const Icon(Icons.feedback),
            label: const Text('提交反馈 / 催更'),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text('重新扫描'),
          ),
        ],
      ),
    );
  }

  Widget _buildFeedbackButton(BuildContext context, String barcode) {
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton.icon(
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => FeedbackScreen(barcode: barcode),
            ),
          );
        },
        icon: const Icon(Icons.feedback_outlined),
        label: const Text('我尝过 / 催更'),
      ),
    );
  }

  Widget _infoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          SizedBox(
            width: 60,
            child: Text(
              label,
              style: const TextStyle(color: Colors.grey, fontSize: 13),
            ),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }

  String _categoryLabel(String category) {
    switch (category) {
      case 'wine':
        return '葡萄酒';
      case 'whisky':
        return '威士忌';
      case 'gin':
        return '金酒';
      default:
        return category;
    }
  }

  Color _verdictColor(String? verdict) {
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

  Color _verdictBgColor(String? verdict) {
    switch (verdict) {
      case 'recommend':
        return const Color(0xFF2E7D32);
      case 'neutral':
        return const Color(0xFFE65100);
      case 'avoid':
        return const Color(0xFFC62828);
      default:
        return const Color(0xFF616161);
    }
  }

  String _formatTimestamp(int seconds) {
    final min = seconds ~/ 60;
    final sec = seconds % 60;
    return '${min.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
  }

  void _showVideoLink(BuildContext context, ReviewData review) {
    // TODO: Get actual BVID from review data to construct URL
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('视频跳转功能开发中...')),
    );
  }
}