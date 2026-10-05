import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'package:mr_sheven/screens/result_screen.dart';
import 'package:mr_sheven/services/api_service.dart';
import 'package:mr_sheven/widgets/loading_dialog.dart';

final ImagePicker _picker = ImagePicker();

/// 拍酒标识别入口（裁决 C12）：拍照/选图 → OCR 中文背标 → 三档匹配 → 结果页。
///
/// 引导文案对齐 06 文档：拍**中文背标**（法定强制印刷、标准字体），
/// 避反光、让背标占满取景框。扫码主页与"查无此码"结果页共用本入口。
Future<void> startLabelScan(BuildContext context) async {
  final source = await showModalBottomSheet<ImageSource>(
    context: context,
    builder: (ctx) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: const Icon(Icons.photo_camera),
            title: const Text('拍摄中文背标'),
            subtitle: const Text('避反光、让背标占满取景框'),
            onTap: () => Navigator.pop(ctx, ImageSource.camera),
          ),
          ListTile(
            leading: const Icon(Icons.photo_library),
            title: const Text('从相册选择'),
            onTap: () => Navigator.pop(ctx, ImageSource.gallery),
          ),
        ],
      ),
    ),
  );
  if (source == null || !context.mounted) return;

  final XFile? file = await _picker.pickImage(
    source: source,
    maxWidth: 1600,
    imageQuality: 85,
  );
  if (file == null || !context.mounted) return;

  final bytes = await file.readAsBytes();
  if (!context.mounted) return;

  final api = context.read<ApiService>();
  // OCR + LLM 匹配耗时较长，给阻塞式加载动画，避免页面"假死"
  final closeLoading = showLoadingDialog(
    context,
    title: '正在识别酒标',
    tips: const [
      '正在上传酒标图片…',
      '正在识别背标文字（OCR）…',
      '正在匹配酒款与博主评测…',
      '快好了，请稍候…',
    ],
  );
  final result = await api.scanLabel(imageBytes: bytes);
  closeLoading();
  if (!context.mounted) return;

  if (result != null) {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ResultScreen(barcode: '', result: result),
      ),
    );
  } else {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(api.error ?? '识别失败，请重试')),
    );
  }
}
