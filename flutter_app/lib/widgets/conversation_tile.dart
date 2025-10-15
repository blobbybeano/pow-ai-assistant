import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/conversation.dart';
import 'avatar_circle.dart';

class ConversationTile extends StatelessWidget {
  const ConversationTile({
    super.key,
    required this.summary,
    required this.onTap,
  });

  final ConversationSummary summary;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final lastMessage = summary.lastMessage;
    final subtitle = lastMessage?.text ?? 'New conversation';
    final timestamp = lastMessage != null
        ? DateFormat('MMM d, h:mm a').format(lastMessage.timestamp)
        : '';

    return ListTile(
      onTap: onTap,
      leading: AvatarCircle(label: summary.displayName),
      title: Row(
        children: [
          Expanded(
            child: Text(
              summary.displayName,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (timestamp.isNotEmpty)
            Text(
              timestamp,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: Colors.black54),
            ),
        ],
      ),
      subtitle: Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Text(
          subtitle,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context)
              .textTheme
              .bodyMedium
              ?.copyWith(color: Colors.black54),
        ),
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _AiBadge(isEnabled: summary.aiEnabled),
          if (summary.unreadCount > 0)
            Container(
              margin: const EdgeInsets.only(top: 6),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: const BoxDecoration(
                color: Color(0xFF246BFD),
                borderRadius: BorderRadius.all(Radius.circular(12)),
              ),
              child: Text(
                summary.unreadCount.toString(),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
        ],
      ),
    );
  }
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
          color: isEnabled ? const Color(0xFF246BFD) : Colors.grey,
        ),
        const SizedBox(width: 4),
        Text(
          isEnabled ? 'AI on' : 'AI off',
          style: Theme.of(context)
              .textTheme
              .bodySmall
              ?.copyWith(color: Colors.black54, fontWeight: FontWeight.w600),
        ),
      ],
    );
  }
}
