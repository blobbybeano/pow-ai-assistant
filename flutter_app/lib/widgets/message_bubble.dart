import 'package:flutter/material.dart';

import '../models/message.dart';
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

    final List<Widget> contentWidgets = [];
    if (isDrafting) {
      contentWidgets.add(
        TypingIndicator(
          dotColor: isInbound ? authorColor : (isPendingAi ? authorColor : Colors.white),
        ),
      );
    } else {
      if (message.hasAttachments) {
        contentWidgets.add(
          _AttachmentGallery(
            attachments: message.attachments,
            isInbound: isInbound,
          ),
        );
      }
      if (message.text.isNotEmpty) {
        if (contentWidgets.isNotEmpty) {
          contentWidgets.add(const SizedBox(height: 8));
        }
        contentWidgets.add(
          Text(
            message.text,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: textColor,
                  height: 1.5,
                ),
          ),
        );
      }
    }

    final hasContent = contentWidgets.isNotEmpty;

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
            ...contentWidgets,
            if (hasContent || isDrafting) const SizedBox(height: 8),
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
  const _AttachmentGallery({required this.attachments, required this.isInbound});

  final List<MessageAttachment> attachments;
  final bool isInbound;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment:
          isInbound ? CrossAxisAlignment.start : CrossAxisAlignment.end,
      children: [
        for (var index = 0; index < attachments.length; index++) ...[
          _AttachmentPreview(
            attachment: attachments[index],
            isInbound: isInbound,
          ),
          if (index != attachments.length - 1) const SizedBox(height: 8),
        ],
      ],
    );
  }
}

class _AttachmentPreview extends StatelessWidget {
  const _AttachmentPreview({required this.attachment, required this.isInbound});

  final MessageAttachment attachment;
  final bool isInbound;

  @override
  Widget build(BuildContext context) {
    if (attachment.isImage && attachment.url.isNotEmpty) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: 280,
            minWidth: 140,
            maxHeight: 320,
          ),
          child: AspectRatio(
            aspectRatio: 4 / 3,
            child: Image.network(
              attachment.url,
              fit: BoxFit.cover,
              errorBuilder: (context, error, stackTrace) => Container(
                color: Colors.black.withOpacity(0.2),
                alignment: Alignment.center,
                child: const Icon(
                  Icons.broken_image_outlined,
                  color: Colors.white70,
                  size: 32,
                ),
              ),
              loadingBuilder: (context, child, progress) {
                if (progress == null) return child;
                return Container(
                  color: Colors.black.withOpacity(0.12),
                  alignment: Alignment.center,
                  child: CircularProgressIndicator(
                    value: progress.expectedTotalBytes != null
                        ? progress.cumulativeBytesLoaded /
                            progress.expectedTotalBytes!
                        : null,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      isInbound ? const Color(0xFF00A884) : Colors.white,
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      );
    }

    final textTheme = Theme.of(context).textTheme;
    final labelColor = isInbound ? Colors.white : const Color(0xFFE9EDEF);
    final background = isInbound
        ? Colors.black.withOpacity(0.14)
        : Colors.white.withOpacity(0.08);
    final border = isInbound
        ? Colors.white.withOpacity(0.12)
        : Colors.white.withOpacity(0.16);
    final displayName = attachment.filename?.trim().isNotEmpty == true
        ? attachment.filename!
        : 'Attachment';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.insert_drive_file,
            color: labelColor.withOpacity(0.8),
            size: 18,
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              displayName,
              style: textTheme.bodySmall?.copyWith(
                color: labelColor,
                fontWeight: FontWeight.w600,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
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
