import 'package:flutter/material.dart';

import '../models/app_user.dart';
import '../models/conversation.dart';

class PendingAiBanner extends StatelessWidget {
  const PendingAiBanner({
    super.key,
    required this.summary,
    required this.onDismissed,
    this.responder,
  });

  final ConversationSummary summary;
  final VoidCallback onDismissed;
  final AppUser? responder;

  @override
  Widget build(BuildContext context) {
    final messagePreview = summary.lastMessage?.previewText() ?? '';
    return Container(
      decoration: BoxDecoration(
        color: const Color(0x332FC6B2),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF00A884)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.smart_toy_rounded, color: Color(0xFF00A884)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                RichText(
                  text: TextSpan(
                    style: const TextStyle(
                      color: Color(0xFFE9EDEF),
                      fontWeight: FontWeight.w600,
                    ),
                    children: [
                      TextSpan(text: 'AI is replying to ${summary.displayName}'),
                      if (responder != null) ...[
                        const TextSpan(text: ' as '),
                        TextSpan(
                          text: responder!.displayName,
                          style: const TextStyle(color: Color(0xFFE2B659)),
                        ),
                      ],
                    ],
                  ),
                ),
                if (messagePreview.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  const Text(
                    'AI response preview',
                    style: TextStyle(
                      color: Color(0xFF5BA4FF),
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    messagePreview,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Color(0xFFB6C1C9),
                      fontSize: 12,
                      height: 1.3,
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 12),
          IconButton(
            onPressed: onDismissed,
            icon: const Icon(Icons.close, size: 20),
            color: const Color(0xFF8696A0),
            tooltip: 'Dismiss',
          ),
        ],
      ),
    );
  }
}
