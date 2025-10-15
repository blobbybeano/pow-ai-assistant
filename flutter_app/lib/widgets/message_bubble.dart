import 'package:flutter/material.dart';

import '../models/message.dart';

class MessageBubble extends StatelessWidget {
  const MessageBubble({
    super.key,
    required this.message,
    required this.isGrouped,
  });

  final ChatMessage message;
  final bool isGrouped;

  @override
  Widget build(BuildContext context) {
    final isInbound = message.isInbound;
    final alignment = isInbound ? Alignment.centerLeft : Alignment.centerRight;
    return Align(
      alignment: alignment,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 320),
        margin: EdgeInsets.only(
          top: isGrouped ? 4 : 12,
          left: isInbound ? 12 : 48,
          right: isInbound ? 48 : 12,
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: isInbound ? Colors.white : null,
          gradient: isInbound
              ? null
              : const LinearGradient(
                  colors: [Color(0xFF246BFD), Color(0xFF4CC9F0)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(isInbound ? 0 : 20),
            topRight: Radius.circular(isInbound ? 20 : 0),
            bottomLeft: const Radius.circular(20),
            bottomRight: const Radius.circular(20),
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.04),
              offset: const Offset(0, 4),
              blurRadius: 12,
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment:
              isInbound ? CrossAxisAlignment.start : CrossAxisAlignment.end,
          children: [
            Text(
              message.text,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: isInbound ? Colors.black87 : Colors.white,
                    height: 1.4,
                  ),
            ),
            const SizedBox(height: 6),
            Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment:
                  isInbound ? MainAxisAlignment.start : MainAxisAlignment.end,
              children: [
                Icon(
                  _iconForAuthor(message.author),
                  size: 14,
                  color: isInbound
                      ? const Color(0xFF246BFD)
                      : Colors.white.withOpacity(0.85),
                ),
                const SizedBox(width: 4),
                Text(
                  message.formattedTime(),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: isInbound
                            ? Colors.black45
                            : Colors.white.withOpacity(0.85),
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ],
            )
          ],
        ),
      ),
    );
  }
}

IconData _iconForAuthor(String author) {
  switch (author) {
    case 'ai':
      return Icons.bolt;
    case 'agent':
      return Icons.person;
    case 'system':
      return Icons.shield_outlined;
    default:
      return Icons.phone_iphone;
  }
}
