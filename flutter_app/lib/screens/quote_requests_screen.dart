import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/quote_request_controller.dart';
import '../models/quote_request.dart';

class QuoteRequestsScreen extends StatelessWidget {
  const QuoteRequestsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<QuoteRequestController>();

    return Scaffold(
      backgroundColor: const Color(0xFF0B141A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111B21),
        foregroundColor: const Color(0xFFE9EDEF),
        title: const Text('Custom Quote Requests'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh',
            onPressed: controller.refresh,
          ),
        ],
      ),
      body: _Body(controller: controller),
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.controller});
  final QuoteRequestController controller;

  @override
  Widget build(BuildContext context) {
    if (controller.isLoading && controller.requests.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    final pending = controller.requests.where((r) => r.isPending).toList();
    final answered = controller.requests.where((r) => !r.isPending).toList();

    if (pending.isEmpty && answered.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle_outline_rounded,
                size: 56, color: const Color(0xFF00A884).withOpacity(0.7)),
            const SizedBox(height: 16),
            const Text(
              'No quote requests',
              style: TextStyle(color: Color(0xFFE9EDEF), fontSize: 18),
            ),
            const SizedBox(height: 8),
            const Text(
              'When a customer needs a custom quote,\nit will appear here.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Color(0xFF8696A0)),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (pending.isNotEmpty) ...[
            _SectionHeader(
              label: 'Waiting for your advice',
              count: pending.length,
              color: const Color(0xFFF59E0B),
            ),
            const SizedBox(height: 8),
            ...pending.map((r) => _QuoteCard(request: r, controller: controller)),
          ],
          if (answered.isNotEmpty) ...[
            if (pending.isNotEmpty) const SizedBox(height: 16),
            _SectionHeader(
              label: 'Answered',
              count: answered.length,
              color: const Color(0xFF8696A0),
            ),
            const SizedBox(height: 8),
            ...answered.map((r) => _QuoteCard(request: r, controller: controller)),
          ],
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.label,
    required this.count,
    required this.color,
  });
  final String label;
  final int count;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(
          label,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w600,
            fontSize: 13,
            letterSpacing: 0.3,
          ),
        ),
        const SizedBox(width: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            '$count',
            style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700),
          ),
        ),
      ],
    );
  }
}

class _QuoteCard extends StatefulWidget {
  const _QuoteCard({required this.request, required this.controller});
  final QuoteRequest request;
  final QuoteRequestController controller;

  @override
  State<_QuoteCard> createState() => _QuoteCardState();
}

class _QuoteCardState extends State<_QuoteCard> {
  late final TextEditingController _adviceCtrl;
  bool _submitting = false;
  bool _dismissing = false;

  @override
  void initState() {
    super.initState();
    _adviceCtrl = TextEditingController(text: widget.request.advice ?? '');
  }

  @override
  void dispose() {
    _adviceCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final advice = _adviceCtrl.text.trim();
    if (advice.isEmpty) return;
    setState(() => _submitting = true);
    final ok = await widget.controller.answer(widget.request.id, advice);
    if (!mounted) return;
    if (!ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Failed to send — please try again.')),
      );
    }
    setState(() => _submitting = false);
  }

  Future<void> _dismiss() async {
    setState(() => _dismissing = true);
    await widget.controller.dismiss(widget.request.id);
    if (mounted) setState(() => _dismissing = false);
  }

  @override
  Widget build(BuildContext context) {
    final req = widget.request;
    final isPending = req.isPending;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF111B21),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isPending
              ? const Color(0xFFF59E0B).withOpacity(0.35)
              : const Color(0x22FFFFFF),
        ),
      ),
      child: Opacity(
        opacity: isPending ? 1.0 : 0.65,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: isPending
                          ? const Color(0xFFF59E0B).withOpacity(0.15)
                          : const Color(0xFF00A884).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      isPending ? 'NEEDS QUOTE' : 'ANSWERED',
                      style: TextStyle(
                        color: isPending
                            ? const Color(0xFFF59E0B)
                            : const Color(0xFF00A884),
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  const Spacer(),
                  Text(
                    _formatTime(req.createdAt),
                    style: const TextStyle(color: Color(0xFF8696A0), fontSize: 12),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                req.convId,
                style: const TextStyle(
                  color: Color(0xFF8696A0),
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                req.description,
                style: const TextStyle(
                  color: Color(0xFFE9EDEF),
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (req.customerMsg.isNotEmpty) ...[
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF0B141A),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.format_quote_rounded,
                          color: Color(0xFF8696A0), size: 16),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          req.customerMsg,
                          style: const TextStyle(
                            color: Color(0xFF8696A0),
                            fontSize: 13,
                            height: 1.4,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              if (req.images.isNotEmpty) ...[
                const SizedBox(height: 10),
                SizedBox(
                  height: 80,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: req.images.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 8),
                    itemBuilder: (context, i) {
                      final img = req.images[i];
                      return ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.memory(
                          base64Decode(img.data),
                          width: 80,
                          height: 80,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(
                            width: 80,
                            height: 80,
                            color: const Color(0xFF243038),
                            child: const Icon(Icons.broken_image_outlined,
                                color: Color(0xFF8696A0)),
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ],
              const SizedBox(height: 14),
              if (isPending) ...[
                TextField(
                  controller: _adviceCtrl,
                  style: const TextStyle(color: Color(0xFFE9EDEF)),
                  maxLines: 3,
                  decoration: InputDecoration(
                    hintText: 'Your advice for the AI… e.g. "£150 for the driveway, £80 for patio"',
                    hintStyle: const TextStyle(color: Color(0xFF8696A0), fontSize: 13),
                    filled: true,
                    fillColor: const Color(0xFF0B141A),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: const EdgeInsets.all(12),
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: _submitting ? null : _submit,
                        icon: _submitting
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white),
                              )
                            : const Icon(Icons.send_rounded, size: 16),
                        label: Text(_submitting ? 'Sending…' : 'Send to AI'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF00A884),
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton(
                      onPressed: _dismissing ? null : _dismiss,
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF8696A0),
                        side: const BorderSide(color: Color(0xFF243038)),
                        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                      ),
                      child: _dismissing
                          ? const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Dismiss'),
                    ),
                  ],
                ),
              ] else ...[
                if (req.advice != null && req.advice!.isNotEmpty) ...[
                  Text(
                    'Your advice:',
                    style: const TextStyle(
                      color: Color(0xFF8696A0),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    req.advice!,
                    style: const TextStyle(color: Color(0xFFE9EDEF), fontSize: 13, height: 1.4),
                  ),
                ],
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerRight,
                  child: OutlinedButton(
                    onPressed: _dismissing ? null : _dismiss,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF8696A0),
                      side: const BorderSide(color: Color(0xFF243038)),
                      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 14),
                    ),
                    child: const Text('Remove'),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _formatTime(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  }
}
