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
            if (message.hasAttachments) ...[
              _AttachmentGallery(
                attachments: message.attachments,
                isInbound: isInbound,
              ),
              if (message.text.isNotEmpty || isDrafting) const SizedBox(height: 12),
            ],
            if (isDrafting)
              TypingIndicator(
                dotColor: isInbound ? authorColor : (isPendingAi ? authorColor : Colors.white),
              )
            else if (message.text.isNotEmpty)
              Text(
                message.text,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: textColor,
                      height: 1.5,
                    ),
              ),
            if (!isDrafting && message.text.isEmpty && !message.hasAttachments)
              Text(
                '(No message content)',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: textColor.withOpacity(0.8),
                      fontStyle: FontStyle.italic,
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
  const _AttachmentGallery({required this.attachments, required this.isInbound});

  final List<ChatAttachment> attachments;
  final bool isInbound;

  @override
  Widget build(BuildContext context) {
    final images = attachments.where((attachment) => attachment.isImage).toList();
    final others = attachments.where((attachment) => !attachment.isImage).toList();

    return Column(
      crossAxisAlignment:
          isInbound ? CrossAxisAlignment.start : CrossAxisAlignment.end,
      children: [
        if (images.isNotEmpty)
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final attachment in images)
                _ImageAttachmentTile(
                  attachment: attachment,
                  isInbound: isInbound,
                ),
            ],
          ),
        if (others.isNotEmpty) ...[
          if (images.isNotEmpty) const SizedBox(height: 8),
          Column(
            crossAxisAlignment:
                isInbound ? CrossAxisAlignment.start : CrossAxisAlignment.end,
            children: [
              for (final attachment in others)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: _FileAttachmentTile(
                    attachment: attachment,
                    isInbound: isInbound,
                  ),
                ),
            ],
          ),
        ],
      ],
    );
  }
}

class _ImageAttachmentTile extends StatelessWidget {
  const _ImageAttachmentTile({required this.attachment, required this.isInbound});

  final ChatAttachment attachment;
  final bool isInbound;

  @override
  Widget build(BuildContext context) {
    final borderRadius = BorderRadius.circular(16);
    return ClipRRect(
      borderRadius: borderRadius,
      child: Container(
        decoration: BoxDecoration(
          border: Border.all(
            color: isInbound ? const Color(0x338696A0) : const Color(0x3300A884),
          ),
        ),
        child: Image.network(
          attachment.url,
          width: 160,
          height: 160,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) {
            return Container(
              width: 160,
              height: 160,
              color: const Color(0xFF111B21),
              alignment: Alignment.center,
              child: const Icon(Icons.broken_image, color: Color(0xFF8696A0)),
            );
          },
        ),
      ),
    );
  }
}

class _FileAttachmentTile extends StatelessWidget {
  const _FileAttachmentTile({required this.attachment, required this.isInbound});

  final ChatAttachment attachment;
  final bool isInbound;

  @override
  Widget build(BuildContext context) {
    final color = isInbound ? const Color(0xFF202C33) : const Color(0xFF005C4B);
    final border = isInbound ? const Color(0x1A8696A0) : const Color(0x3300A884);
    return Container(
      constraints: const BoxConstraints(maxWidth: 240),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.insert_drive_file, color: Color(0xFFE9EDEF), size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              attachment.filename ?? attachment.label(),
              style: const TextStyle(color: Color(0xFFE9EDEF)),
              maxLines: 1,
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
