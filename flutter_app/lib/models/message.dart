import 'package:intl/intl.dart';

class ChatMessage {
  ChatMessage({
    required this.id,
    required this.text,
    required this.author,
    required this.direction,
    required this.timestamp,
    required this.via,
    required this.status,
    this.attachments = const [],
    this.mediaUrls = const [],
    this.scheduledSendAt,
    this.sentAt,
    this.transportSid,
    this.error,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    DateTime? _parseDate(String? value) =>
        value != null ? DateTime.parse(value).toLocal() : null;
    return ChatMessage(
      id: json['id'] as String,
      text: json['text'] as String,
      author: json['author'] as String,
      direction: json['direction'] as String,
      timestamp: DateTime.parse(json['timestamp'] as String).toLocal(),
      via: json['via'] as String? ?? 'whatsapp',
      status: json['status'] as String? ?? 'sent',
      attachments: _parseAttachments(json['attachments']),
      mediaUrls: _parseMediaUrls(json['media_urls']),
      scheduledSendAt: _parseDate(json['scheduledSendAt'] as String?),
      sentAt: _parseDate(json['sentAt'] as String?),
      transportSid: json['transportSid'] as String?,
      error: json['error'] as String?,
    );
  }

  final String id;
  final String text;
  final String author;
  final String direction;
  final DateTime timestamp;
  final String via;
  final String status;
  final List<MessageAttachment> attachments;
  final List<String> mediaUrls;
  final DateTime? scheduledSendAt;
  final DateTime? sentAt;
  final String? transportSid;
  final String? error;

  bool get isInbound => direction == 'inbound';

  bool get hasAttachments => attachments.isNotEmpty;

  DateTime get displayTimestamp => sentAt ?? scheduledSendAt ?? timestamp;

  String formattedTime() => DateFormat.jm().format(displayTimestamp);

  bool get isScheduled => status == 'scheduled';
  bool get isFailed => status == 'failed';
  bool get isDrafting => status == 'drafting';
  bool get isCancelled => status == 'cancelled';
  bool get isPending => status == 'scheduled' || status == 'sending' || isDrafting;

  String? statusLabel() {
    switch (status) {
      case 'drafting':
        return 'Typing…';
      case 'scheduled':
        if (scheduledSendAt == null) return 'Scheduled to send soon';
        final now = DateTime.now();
        final diff = scheduledSendAt!.difference(now);
        if (diff.inSeconds <= 0) {
          return 'Sending shortly…';
        }
        final totalSeconds = diff.inSeconds;
        final minutes = totalSeconds ~/ 60;
        final seconds = totalSeconds % 60;
        final secondsLabel = seconds.toString().padLeft(2, '0');
        return 'Sending in $minutes:$secondsLabel';
      case 'failed':
        return error != null && error!.isNotEmpty ? 'Failed: $error' : 'Failed to send';
      case 'cancelled':
        return error != null && error!.isNotEmpty ? error : 'Cancelled';
      case 'sending':
        return 'Sending…';
      default:
        return null;
    }
  }

  String? attachmentLabel() {
    if (attachments.isEmpty) return null;
    final first = attachments.first;
    if (first.isImage) return 'Photo';
    final name = first.filename;
    if (name.isNotEmpty) return 'Attachment: $name';
    return 'Attachment';
  }
}

class MessageAttachment {
  MessageAttachment({required this.value, this.contentType});

  factory MessageAttachment.fromJson(dynamic json) {
    if (json is String && json.trim().isNotEmpty) {
      return MessageAttachment(value: json.trim());
    }
    if (json is Map<String, dynamic>) {
      final url = json['url'] as String?;
      final path = json['path'] as String?;
      final localPath = json['local_path'] as String?;
      final contentType = json['content_type'] as String? ?? json['mime_type'] as String?;
      final resolved = (url ?? path ?? localPath)?.toString().trim();
      if (resolved != null && resolved.isNotEmpty) {
        return MessageAttachment(value: resolved, contentType: contentType);
      }
    }
    return MessageAttachment(value: '');
  }

  final String value;
  final String? contentType;

  bool get isImage {
    final mime = contentType?.toLowerCase();
    if (mime != null && mime.startsWith('image/')) return true;
    final lowerValue = value.toLowerCase();
    return lowerValue.endsWith('.jpg') ||
        lowerValue.endsWith('.jpeg') ||
        lowerValue.endsWith('.png') ||
        lowerValue.endsWith('.gif') ||
        lowerValue.endsWith('.webp');
  }

  String get filename {
    final sanitized = value.replaceAll('\\\\', '/');
    final parts = sanitized.split('/');
    return parts.isNotEmpty ? parts.last : value;
  }

  String resolvedUrl(String apiBaseUrl) {
    final trimmed = value.trim();
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      return trimmed;
    }
    final sanitized = trimmed.replaceAll('\\\\', '/');
    final fileName = sanitized.split('/').isNotEmpty ? sanitized.split('/').last : sanitized;
    final base = Uri.parse(apiBaseUrl);
    return base.resolve('/uploads/$fileName').toString();
  }
}

List<MessageAttachment> _parseAttachments(dynamic raw) {
  if (raw is! List) return const [];
  return raw
      .map((entry) => MessageAttachment.fromJson(entry))
      .where((att) => att.value.isNotEmpty)
      .toList();
}

List<String> _parseMediaUrls(dynamic raw) {
  if (raw is! List) return const [];
  return raw
      .whereType<String>()
      .map((url) => url.trim())
      .where((url) => url.isNotEmpty)
      .toList();
}
