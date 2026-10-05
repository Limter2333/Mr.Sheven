import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:provider/provider.dart';
import 'package:mr_sheven/services/api_service.dart';
import 'package:mr_sheven/services/label_scan_flow.dart';
import 'package:mr_sheven/screens/result_screen.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  MobileScannerController? _controller;
  bool _isScanning = true;
  bool _isFlashOn = false;

  @override
  void initState() {
    super.initState();
    _controller = MobileScannerController(
      detectionSpeed: DetectionSpeed.normal,
      facing: CameraFacing.back,
    );
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  void _onBarcodeDetected(BarcodeCapture capture) async {
    if (!_isScanning) return;

    final barcodes = capture.barcodes;
    if (barcodes.isEmpty) return;

    final code = barcodes.first.rawValue;
    if (code == null || code.isEmpty) return;

    // Validate barcode format (EAN-13/UPC)
    if (!_isValidBarcode(code)) {
      _showSnackBar('无效的条码格式，请对准酒瓶上的条形码');
      return;
    }

    setState(() => _isScanning = false);

    final api = context.read<ApiService>();
    final result = await api.scanBarcode(code);

    if (!mounted) return;

    if (result != null) {
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ResultScreen(barcode: code, result: result),
        ),
      ).then((_) {
        setState(() => _isScanning = true);
      });
    } else {
      _showSnackBar(api.error ?? '扫描失败，请重试');
      setState(() => _isScanning = true);
    }
  }

  bool _isValidBarcode(String code) {
    // UPC-A: 12 digits, EAN-13: 13 digits, ITF-14 (国内): 14 digits
    final clean = code.replaceAll(RegExp(r'[^0-9]'), '');
    return clean.length >= 12 && clean.length <= 14;
  }

  void _showManualInput() {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('手动输入条码'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: '输入 12-13 位数字条码',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              final code = controller.text.trim();
              Navigator.pop(ctx);
              if (_isValidBarcode(code)) {
                _onBarcodeDetected(BarcodeCapture(
                  barcodes: [Barcode(rawValue: code, format: BarcodeFormat.ean13)],
                ));
              } else {
                _showSnackBar('条码格式无效，需 12-13 位数字');
              }
            },
            child: const Text('查询'),
          ),
        ],
      ),
    );
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 2)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mr.Sheven 酒评速查'),
        actions: [
          IconButton(
            icon: Icon(_isFlashOn ? Icons.flash_on : Icons.flash_off),
            onPressed: () {
              _controller?.toggleTorch();
              setState(() => _isFlashOn = !_isFlashOn);
            },
          ),
        ],
      ),
      body: Column(
        children: [
          // Scanner area
          Expanded(
            flex: 4,
            child: Stack(
              children: [
                MobileScanner(
                  controller: _controller!,
                  onDetect: _onBarcodeDetected,
                ),
                // Scan overlay
                Center(
                  child: Container(
                    width: 280,
                    height: 180,
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: theme.colorScheme.primary,
                        width: 2,
                      ),
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
                // Status indicator
                if (!_isScanning)
                  Container(
                    color: Colors.black54,
                    child: const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          CircularProgressIndicator(color: Colors.white),
                          SizedBox(height: 16),
                          Text(
                            '正在查询条码…',
                            style: TextStyle(color: Colors.white, fontSize: 15),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),

          // Instructions + manual input
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.qr_code_scanner,
                  size: 28,
                  color: theme.colorScheme.primary,
                ),
                const SizedBox(height: 4),
                Text(
                  '将酒瓶条形码对准扫描框',
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(height: 2),
                Text(
                  '支持 EAN-13 / UPC-A 格式',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 8),
                TextButton.icon(
                  onPressed: _showManualInput,
                  icon: const Icon(Icons.keyboard, size: 18),
                  label: const Text('手动输入条码'),
                ),
                const SizedBox(height: 4),
                TextButton.icon(
                  onPressed: () => startLabelScan(context),
                  icon: const Icon(Icons.photo_camera_back, size: 18),
                  label: const Text('拍酒标识别（推荐）'),
                ),
                Text(
                  '进口酒条码常查不到？拍中文背标也能识别',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}