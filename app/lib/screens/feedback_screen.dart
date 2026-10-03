import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:mr_sheven/services/api_service.dart';

class FeedbackScreen extends StatefulWidget {
  final String barcode;

  const FeedbackScreen({super.key, required this.barcode});

  @override
  State<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends State<FeedbackScreen> {
  final _formKey = GlobalKey<FormState>();
  final _feedbackController = TextEditingController();
  String? _selectedTaste;
  bool _isSubmitting = false;

  final _tasteOptions = [
    '果香型',
    '花香型',
    '烟熏型',
    '泥煤型',
    '辛辣型',
    '甜润型',
    '干型',
    '其他',
  ];

  @override
  void dispose() {
    _feedbackController.dispose();
    super.dispose();
  }

  Future<void> _submitFeedback() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isSubmitting = true);

    final api = context.read<ApiService>();
    final success = await api.submitFeedback(
      barcode: widget.barcode,
      feedback: _feedbackController.text,
      taste: _selectedTaste,
    );

    setState(() => _isSubmitting = false);

    if (!mounted) return;

    if (success) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('感谢您的反馈！')),
      );
      Navigator.pop(context);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('提交失败，请重试')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('反馈 / 催更'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Barcode info
              Card(
                child: ListTile(
                  leading: const Icon(Icons.qr_code),
                  title: const Text('条码'),
                  subtitle: Text(widget.barcode),
                ),
              ),
              const SizedBox(height: 16),

              // Taste selection
              Text(
                '口感标签（可选）',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: _tasteOptions.map((taste) {
                  final isSelected = _selectedTaste == taste;
                  return FilterChip(
                    label: Text(taste),
                    selected: isSelected,
                    onSelected: (selected) {
                      setState(() {
                        _selectedTaste = selected ? taste : null;
                      });
                    },
                  );
                }).toList(),
              ),
              const SizedBox(height: 16),

              // Feedback text
              Text(
                '您的反馈',
                style: theme.textTheme.titleMedium,
              ),
              const SizedBox(height: 8),
              TextFormField(
                controller: _feedbackController,
                maxLines: 5,
                decoration: const InputDecoration(
                  hintText: '说说您对这款酒的看法，或者催促我们收录某款酒...',
                  border: OutlineInputBorder(),
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return '请输入反馈内容';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 24),

              // Submit button
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton(
                  onPressed: _isSubmitting ? null : _submitFeedback,
                  child: _isSubmitting
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('提交反馈'),
                ),
              ),
              const SizedBox(height: 16),

              // Hint
              Text(
                '提示：您的反馈将帮助我们优先收录更多酒款的评测数据。',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}