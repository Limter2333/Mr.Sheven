import 'dart:async';

import 'package:flutter/material.dart';

/// 识别链路加载弹窗（裁决 C12：OCR + LLM 匹配耗时可达数秒~数十秒）。
///
/// 阻塞式（点外面不关闭），带脉冲动画与轮播状态文案，避免页面"假死"。
/// 返回关闭函数，调用方在任务结束后务必调用（幂等）。
VoidCallback showLoadingDialog(
  BuildContext context, {
  String title = '正在识别…',
  List<String> tips = const ['请稍候，马上就好…'],
}) {
  final navigator = Navigator.of(context, rootNavigator: true);
  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _LoadingDialog(title: title, tips: tips),
  );
  var closed = false;
  return () {
    if (closed) return;
    closed = true;
    navigator.pop();
  };
}

class _LoadingDialog extends StatefulWidget {
  const _LoadingDialog({required this.title, required this.tips});

  final String title;
  final List<String> tips;

  @override
  State<_LoadingDialog> createState() => _LoadingDialogState();
}

class _LoadingDialogState extends State<_LoadingDialog>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;
  Timer? _tipTimer;
  int _tipIndex = 0;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);
    if (widget.tips.length > 1) {
      _tipTimer = Timer.periodic(const Duration(seconds: 2), (_) {
        if (mounted) {
          setState(() => _tipIndex = (_tipIndex + 1) % widget.tips.length);
        }
      });
    }
  }

  @override
  void dispose() {
    _tipTimer?.cancel();
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Dialog(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 转圈 + 图标脉冲，视觉上表达"在动"
            SizedBox(
              width: 88,
              height: 88,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  const SizedBox(
                    width: 88,
                    height: 88,
                    child: CircularProgressIndicator(strokeWidth: 3),
                  ),
                  FadeTransition(
                    opacity: Tween<double>(begin: 0.55, end: 1.0).animate(_pulse),
                    child: ScaleTransition(
                      scale: Tween<double>(begin: 0.92, end: 1.08)
                          .animate(_pulse),
                      child: Icon(
                        Icons.wine_bar,
                        size: 40,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Text(widget.title, style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 300),
              child: Text(
                widget.tips[_tipIndex],
                key: ValueKey(_tipIndex),
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
