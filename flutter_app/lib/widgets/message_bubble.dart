import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/message.dart';
import '../services/chat_api_client.dart';
import 'typing_indicator.dart';

class MessageBubble extends StatelessWidget {
  const MessageBubble({
    required this.message,
    required this.isGrouped,
    this.action,
    super.key,
  });

  final ChatMessage message;
  final bool isGrouped;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final apiBaseUrl = context.read<ChatApiClient>().baseUrl;
    final imageAttachments =
        message.attachments.where((attachment) => attachment.isImage).toList();
    final hasText = message.text.isNotEmpty;
    if (message.author == 'system') {
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: Colors.grey.shade200,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                child: Text(
                  message.text,
                  textAlign: TextAlign.center,
                  style: Theme.of(context)
                      .textTheme
                      .bodyMedium
                      ?.copyWith(color: Colors.black87, height: 1.4),
                ),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              message.formattedTime(),
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: Colors.black45, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      );
    }

    final isInbound = message.isInbound;
    final alignment = isInbound ? Alignment.centerLeft : Alignment.centerRight;
    final statusLabel = message.statusLabel();
    final isDrafting = message.isDrafting;
    final isPendingAi = message.author == 'ai' && message.isPending;

    final bubbleColor = isPendingAi
        ? const Color(0xFFFFC857)
        : isInbound
            ? const Color(0xFF202C33)
            : const Color(0xFF005C4B);
    final authorColor = isPendingAi
        ? const Color(0xFF7A5800)
        : isInbound
            ? const Color(0xFF00A884)
            : Colors.white;
    final textColor = isPendingAi ? const Color(0xFF2A1A00) : Colors.white;
    final borderColor = isPendingAi
        ? const Color(0xFFFFE29F)
        : isInbound
            ? const Color(0x1A8696A0)
            : const Color(0x3300A884);

    return Align(
      alignment: alignment,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 360),
        margin: EdgeInsets.only(
          top: isGrouped ? 4 : 12,
          left: isInbound ? 12 : 64,
          right: isInbound ? 64 : 12,
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(isInbound ? 4 : 18),
            topRight: Radius.circular(isInbound ? 18 : 4),
            bottomLeft: const Radius.circular(18),
            bottomRight: const Radius.circular(18),
          ),
          border: Border.all(color: borderColor),
        ),
        child: Column(
          crossAxisAlignment:
              isInbound ? CrossAxisAlignment.start : CrossAxisAlignment.end,
          children: [
            if (imageAttachments.isNotEmpty) ...[
              _AttachmentGallery(
                attachments: imageAttachments,
                apiBaseUrl: apiBaseUrl,
              ),
              if (hasText) const SizedBox(height: 8),
            ],
            if (isDrafting)
              TypingIndicator(
                dotColor: isInbound ? authorColor : (isPendingAi ? authorColor : Colors.white),
              )
            else if (hasText)
              Text(
                message.text,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: textColor,
                      height: 1.5,
                    ),
              ),
            const SizedBox(height: 8),
            Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment:
                  isInbound ? MainAxisAlignment.start : MainAxisAlignment.end,
              children: [
                Icon(
                  _iconForAuthor(message.author),
                  size: 14,
                  color: authorColor,
                ),
                const SizedBox(width: 6),
                Text(
                  _authorLabel(message.author),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: authorColor,
                        fontWeight: FontWeight.w600,
                      ),
                ),
                const SizedBox(width: 8),
                Text(
                  message.formattedTime(),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: const Color(0xFFB9C5CC),
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ],
            ),
            if (statusLabel != null) ...[
              const SizedBox(height: 8),
              Row(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment:
                    isInbound ? MainAxisAlignment.start : MainAxisAlignment.end,
                children: [
                  Icon(
                    message.isFailed
                        ? Icons.error_outline
                        : Icons.schedule_outlined,
                    size: 14,
                    color: authorColor,
                  ),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      statusLabel,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: authorColor,
                            fontWeight: FontWeight.w600,
                          ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              )
            ],
            if (action != null) ...[
              const SizedBox(height: 8),
              Align(
                alignment:
                    isInbound ? Alignment.centerLeft : Alignment.centerRight,
                child: action!,
              ),
            ]
          ],
        ),
      ),
    );
  }
}

class _AttachmentGallery extends StatelessWidget {
  const _AttachmentGallery({required this.attachments, required this.apiBaseUrl});

  final List<MessageAttachment> attachments;
  final String apiBaseUrl;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final attachment in attachments) ...[
          ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: Container(
              color: const Color(0xFF0B141A),
              child: AspectRatio(
                aspectRatio: 4 / 3,
                child: Image.network(
                  attachment.resolvedUrl(apiBaseUrl),
                  fit: BoxFit.cover,
                  loadingBuilder: (context, child, progress) {
                    if (progress == null) return child;
                    return const Center(
                      child: SizedBox(
                        width: 32,
                        height: 32,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          color: Color(0xFF00A884),
                        ),
                      ),
                    );
                  },
                  errorBuilder: (_, __, ___) => Container(
                    color: const Color(0xFF182229),
                    alignment: Alignment.center,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: const [
                        Icon(Icons.broken_image_outlined, color: Color(0xFF8696A0), size: 28),
                        SizedBox(height: 6),
                        Text(
                          'Could not load image',
                          style: TextStyle(color: Color(0xFF8696A0), fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
        ]
      ],
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

String _authorLabel(String author) {
  switch (author) {
    case 'ai':
      return 'AI';
    case 'agent':
      return 'Agent';
    case 'customer':
      return 'Customer';
    case 'system':
      return 'System';
    default:
      return author;
  }
}
