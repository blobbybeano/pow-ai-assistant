import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/conversation.dart';
import '../models/message.dart';
import 'avatar_circle.dart';

class ConversationTile extends StatelessWidget {
  const ConversationTile({
    required this.summary,
    required this.onTap,
    this.isSelected = false,
    this.avatarImage,
    super.key,
  });

  final ConversationSummary summary;
  final VoidCallback onTap;
  final bool isSelected;
  final ImageProvider<Object>? avatarImage;

  @override
  Widget build(BuildContext context) {
    final lastMessage = summary.lastMessage;
    final subtitle = _buildSubtitle(lastMessage);
    final timestamp = lastMessage != null
        ? DateFormat('h:mm a').format(lastMessage.displayTimestamp)
        : '';

    final backgroundColor = isSelected ? const Color(0x3320A884) : const Color(0x14202C33);
    final borderColor = isSelected ? const Color(0x6600A884) : Colors.transparent;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: borderColor, width: 1.5),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AvatarCircle(label: summary.displayName, size: 44, image: avatarImage),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          summary.displayName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Color(0xFFE9EDEF),
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          ),
                        ),
                      ),
                      if (timestamp.isNotEmpty)
                        Text(
                          timestamp,
                          style: const TextStyle(
                            color: Color(0xFF8696A0),
                            fontSize: 12,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Color(0xFF8696A0),
                      fontSize: 13,
                      height: 1.3,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      _AiBadge(isEnabled: summary.aiEnabled),
                      const Spacer(),
                      if (summary.unreadCount > 0)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: const BoxDecoration(
                            color: Color(0xFF00A884),
                            borderRadius: BorderRadius.all(Radius.circular(999)),
                          ),
                          child: Text(
                            summary.unreadCount.toString(),
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _buildSubtitle(ChatMessage? message) {
  if (message == null) return 'New conversation';
  final statusLabel = message.statusLabel();
  final summary = message.summaryText();
  if (statusLabel != null && !message.isInbound) {
    return summary.isNotEmpty ? '$statusLabel • $summary' : statusLabel;
  }
  return summary.isNotEmpty ? summary : 'Message';
}

class _AiBadge extends StatelessWidget {
  const _AiBadge({required this.isEnabled});

  final bool isEnabled;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(
          isEnabled ? Icons.bolt : Icons.bolt_outlined,
          size: 16,
          color: isEnabled ? const Color(0xFF00A884) : const Color(0xFF8696A0),
        ),
        const SizedBox(width: 6),
        Text(
          isEnabled ? 'AI on' : 'AI off',
          style: const TextStyle(
            color: Color(0xFF8696A0),
            fontWeight: FontWeight.w600,
            fontSize: 12,
          ),
        ),
      ],
    );
  }
}
