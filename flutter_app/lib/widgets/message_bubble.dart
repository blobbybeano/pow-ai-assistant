import 'package:flutter/material.dart';

import '../models/message.dart';
import 'typing_indicator.dart';

const _apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://127.0.0.1:5002',
);

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
    final attachments = message.attachments;

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
            if (isDrafting)
              TypingIndicator(
                dotColor: isInbound ? authorColor : (isPendingAi ? authorColor : Colors.white),
              )
            else ...[
              if (message.text.isNotEmpty)
                Text(
                  message.text,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: textColor,
                        height: 1.5,
                      ),
                ),
              if (attachments.isNotEmpty) ...[
                if (message.text.isNotEmpty) const SizedBox(height: 8),
                _AttachmentsGrid(
                  attachments: attachments,
                  isInbound: isInbound,
                  textColor: textColor,
                ),
              ],
              if (message.text.isNotEmpty || attachments.isNotEmpty)
                const SizedBox(height: 8),
            ],
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

class _AttachmentsGrid extends StatelessWidget {
  const _AttachmentsGrid({
    required this.attachments,
    required this.isInbound,
    required this.textColor,
  });

  final List<String> attachments;
  final bool isInbound;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment:
          isInbound ? CrossAxisAlignment.start : CrossAxisAlignment.end,
      children: attachments
          .map(
            (attachment) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _AttachmentPreview(
                attachment: attachment,
                textColor: textColor,
              ),
            ),
          )
          .toList(),
    );
  }
}

class _AttachmentPreview extends StatelessWidget {
  const _AttachmentPreview({
    required this.attachment,
    required this.textColor,
  });

  final String attachment;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    final imageUrl = _resolveAttachmentUrl(attachment);
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.black.withOpacity(0.1),
          border: Border.all(color: Colors.white24),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: 240,
            maxHeight: 260,
          ),
          child: AspectRatio(
            aspectRatio: 4 / 5,
            child: Image.network(
              imageUrl,
              fit: BoxFit.cover,
              errorBuilder: (context, error, stackTrace) => Container(
                color: Colors.black26,
                alignment: Alignment.center,
                padding: const EdgeInsets.all(12),
                child: Text(
                  'Unable to load image',
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: textColor),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

String _resolveAttachmentUrl(String attachment) {
  if (attachment.startsWith('http://') || attachment.startsWith('https://')) {
    return attachment;
  }

  const uploadsMarker = '/uploads/';
  final uploadsIndex = attachment.indexOf(uploadsMarker);
  final normalizedPath = uploadsIndex != -1
      ? attachment.substring(uploadsIndex)
      : (attachment.startsWith('/') ? attachment : '/$attachment');

  return '$_apiBaseUrl$normalizedPath';
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
