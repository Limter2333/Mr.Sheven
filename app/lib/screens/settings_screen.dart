import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:mr_sheven/screens/feedback_screen.dart';
import 'package:mr_sheven/services/api_service.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final api = context.watch<ApiService>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('设置'),
      ),
      body: ListView(
        children: [
          // Server connection section（同源自动检测；仅异常时手动指定，地址不显式写出）
          const _SectionHeader(title: '连接'),
          ListTile(
            leading: const Icon(Icons.dns_outlined),
            title: const Text('服务器地址'),
            subtitle: const Text('自动检测（点击可手动指定）'),
            trailing: const Icon(Icons.edit_outlined),
            onTap: () => _showServerDialog(context, api),
          ),
          const Divider(),

          // App info section
          const _SectionHeader(title: '关于'),
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('关于 Mr.Sheven'),
            subtitle: const Text('酒类评测速查 v1.0.0'),
            onTap: () => _showAboutDialog(context),
          ),
          const Divider(),

          // Data source section
          const _SectionHeader(title: '数据来源'),
          const ListTile(
            leading: Icon(Icons.source),
            title: Text('数据来源'),
            subtitle: Text('B站酒类测评博主视频自动抽取'),
          ),
          const ListTile(
            leading: Icon(Icons.update),
            title: Text('数据更新'),
            subtitle: Text('每日自动更新（21:30 爬取，22:00 处理）'),
          ),
          const Divider(),

          // Privacy section
          const _SectionHeader(title: '隐私与权限'),
          const ListTile(
            leading: Icon(Icons.camera_alt),
            title: Text('相机权限'),
            subtitle: Text('用于扫描条形码、拍摄/选取酒标图片'),
            trailing: Icon(Icons.check_circle, color: Colors.green),
          ),
          ListTile(
            leading: const Icon(Icons.privacy_tip),
            title: const Text('隐私政策'),
            onTap: () => _showPrivacyPolicy(context),
          ),
          const Divider(),

          // Feedback
          const _SectionHeader(title: '反馈'),
          ListTile(
            leading: const Icon(Icons.bug_report),
            title: const Text('报告问题'),
            subtitle: const Text('遇到 bug？告诉我们'),
            onTap: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const FeedbackScreen(barcode: ''),
                ),
              );
            },
          ),
          ListTile(
            leading: const Icon(Icons.star),
            title: const Text('给我们评分'),
            subtitle: const Text('如果觉得好用，给我们一个好评吧'),
            onTap: () async {
              await Clipboard.setData(
                const ClipboardData(text: 'https://github.com/Limter2333'),
              );
              if (!context.mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('已将链接复制到粘贴板，复制到浏览器使用')),
              );
            },
          ),
          const SizedBox(height: 32),

          // Footer
          Center(
            child: Text(
              'Mr.Sheven © 2026\n扫码 + 拍酒标识别',
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  void _showServerDialog(BuildContext context, ApiService api) {
    final controller = TextEditingController(text: api.baseUrl);
    showDialog<void>(
      context: context,
      builder: (ctx) {
        String? error;
        return StatefulBuilder(
          builder: (ctx, setState) => AlertDialog(
            title: const Text('服务器地址'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: controller,
                  keyboardType: TextInputType.url,
                  decoration: InputDecoration(
                    hintText: 'https://…',
                    helperText: '留空则自动检测；异常时可手动指定服务地址',
                    errorText: error,
                  ),
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () {
                  controller.text = ApiService.defaultBaseUrl;
                  setState(() => error = null);
                },
                child: const Text('恢复默认'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: () {
                  final url = controller.text.trim();
                  if (!ApiService.isValidBaseUrl(url)) {
                    setState(() => error = '格式不对，应形如 http://主机:端口');
                    return;
                  }
                  api.setBaseUrl(url);
                  Navigator.pop(ctx);
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('服务器地址已保存')),
                  );
                },
                child: const Text('保存'),
              ),
            ],
          ),
        );
      },
    );
  }

  void _showAboutDialog(BuildContext context) {
    showAboutDialog(
      context: context,
      applicationName: 'Mr.Sheven 酒评速查',
      applicationVersion: 'v1.0.0',
      applicationIcon: const Icon(Icons.wine_bar, size: 48),
      children: [
        const Text('在商超拿起一瓶酒扫码，立刻看到多位B站酒类博主对它的评测结论。'),
        const SizedBox(height: 16),
        const Text('数据来源：B站酒类测评博主视频自动抽取'),
        const Text('技术栈：Flutter + FastAPI + MySQL'),
      ],
    );
  }

  void _showPrivacyPolicy(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('隐私政策'),
        content: const SingleChildScrollView(
          child: Text(
            'Mr.Sheven 酒评速查 隐私政策\n\n'
            '1. 数据收集\n'
            '   - 本应用仅收集扫码/识别记录（条码、酒款、时间）用于服务优化\n'
            '   - 不收集个人身份信息\n'
            '   - 不收集位置信息\n\n'
            '2. 相机与图片\n'
            '   - 相机用于扫描条形码、拍摄酒标图片\n'
            '   - 酒标图片仅用于识别酒款文字，识别完成后不保存图片\n'
            '   - 不将图片用于其他用途或提供给第三方\n\n'
            '3. 数据存储\n'
            '   - 扫码记录存储在安全的服务器上\n'
            '   - 不与第三方共享用户数据\n\n'
            '4. 联系我们\n'
            '   - 如有隐私问题，请通过应用内反馈联系我们',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;

  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Text(
        title,
        style: Theme.of(context).textTheme.titleSmall?.copyWith(
              color: Theme.of(context).colorScheme.primary,
              fontWeight: FontWeight.bold,
            ),
      ),
    );
  }
}