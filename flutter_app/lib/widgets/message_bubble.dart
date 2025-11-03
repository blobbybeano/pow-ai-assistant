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
    final hasText = message.text.trim().isNotEmpty;
    final hasAttachments = message.attachments.isNotEmpty;

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
              if (hasAttachments)
                _MessageAttachments(
                  attachments: message.attachments,
                  isInbound: isInbound,
                ),
              if (hasAttachments && hasText) const SizedBox(height: 8),
              if (hasText)
                Text(
                  message.text,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: textColor,
                        height: 1.5,
                      ),
                ),
            ],
            if (hasAttachments || hasText || isDrafting) const SizedBox(height: 8),
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

class _MessageAttachments extends StatelessWidget {
  const _MessageAttachments({
    required this.attachments,
    required this.isInbound,
  });

  final List<ChatAttachment> attachments;
  final bool isInbound;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment:
          isInbound ? CrossAxisAlignment.start : CrossAxisAlignment.end,
      children: [
        for (var i = 0; i < attachments.length; i++)
          Padding(
            padding: EdgeInsets.only(bottom: i == attachments.length - 1 ? 0 : 8),
            child: _AttachmentPreview(attachment: attachments[i]),
          ),
      ],
    );
  }
}

class _AttachmentPreview extends StatelessWidget {
  const _AttachmentPreview({required this.attachment});

  final ChatAttachment attachment;

  @override
  Widget build(BuildContext context) {
    final displayUrl = attachment.displayUrl;
    if (attachment.isImage && displayUrl != null) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 120, maxHeight: 260, minWidth: 120),
          child: Image.network(
            displayUrl,
            fit: BoxFit.cover,
            width: double.infinity,
            loadingBuilder: (context, child, progress) {
              if (progress == null) return child;
              final totalBytes = progress.expectedTotalBytes;
              final value = totalBytes != null && totalBytes > 0
                  ? progress.cumulativeBytesLoaded / totalBytes
                  : null;
              return _AttachmentPlaceholder(
                icon: Icons.image,
                label: 'Loading image…',
                progress: value,
              );
            },
            errorBuilder: (context, error, stackTrace) => const _AttachmentPlaceholder(
              icon: Icons.broken_image,
              label: 'Image unavailable',
            ),
          ),
        ),
      );
    }

    final label = attachment.filename?.isNotEmpty == true
        ? attachment.filename!
        : (attachment.isImage ? 'Image attachment' : 'Attachment');
    final icon = attachment.isImage ? Icons.image : Icons.insert_drive_file;

    return _AttachmentPlaceholder(icon: icon, label: label);
  }
}

class _AttachmentPlaceholder extends StatelessWidget {
  const _AttachmentPlaceholder({
    required this.icon,
    required this.label,
    this.progress,
  });

  final IconData icon;
  final String label;
  final double? progress;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(minHeight: 120),
      decoration: BoxDecoration(
        color: Colors.black.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(icon, color: Colors.white70, size: 32),
          const SizedBox(height: 12),
          Text(
            label,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Colors.white70,
                  height: 1.3,
                ),
          ),
          if (progress != null) ...[
            const SizedBox(height: 12),
            LinearProgressIndicator(
              value: progress!.clamp(0.0, 1.0).toDouble(),
              backgroundColor: Colors.white24,
              valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF00A884)),
              minHeight: 4,
            ),
          ],
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
