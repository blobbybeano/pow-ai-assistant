import 'package:intl/intl.dart';

class ChatAttachment {
  ChatAttachment({
    required this.id,
    required this.contentType,
    this.sourceUrl,
    this.filename,
    this.proxyUrl,
    this.cachedPath,
  });

  factory ChatAttachment.fromJson(Map<String, dynamic> json) {
    return ChatAttachment(
      id: json['id'] as String,
      contentType: json['contentType'] as String? ?? 'application/octet-stream',
      sourceUrl: json['sourceUrl'] as String?,
      filename: json['filename'] as String?,
      proxyUrl: json['proxyUrl'] as String?,
      cachedPath: json['cachedPath'] as String?,
    );
  }

  final String id;
  final String contentType;
  final String? sourceUrl;
  final String? filename;
  final String? proxyUrl;
  final String? cachedPath;

  bool get isImage => contentType.startsWith('image/');

  String? get displayUrl => proxyUrl ?? sourceUrl;
}

class ChatMessage {
  ChatMessage({
    required this.id,
    required this.text,
    required this.author,
    required this.direction,
    required this.timestamp,
    required this.via,
    required this.status,
    required this.attachments,
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
      scheduledSendAt: _parseDate(json['scheduledSendAt'] as String?),
      sentAt: _parseDate(json['sentAt'] as String?),
      transportSid: json['transportSid'] as String?,
      error: json['error'] as String?,
      attachments: (json['attachments'] as List<dynamic>? ?? [])
          .map((attachment) =>
              ChatAttachment.fromJson(attachment as Map<String, dynamic>))
          .toList(),
    );
  }

  final String id;
  final String text;
  final String author;
  final String direction;
  final DateTime timestamp;
  final String via;
  final String status;
  final List<ChatAttachment> attachments;
  final DateTime? scheduledSendAt;
  final DateTime? sentAt;
  final String? transportSid;
  final String? error;

  bool get isInbound => direction == 'inbound';

  DateTime get displayTimestamp => sentAt ?? scheduledSendAt ?? timestamp;

  bool get hasAttachments => attachments.isNotEmpty;

  String formattedTime() => DateFormat.jm().format(displayTimestamp);

  bool get isScheduled => status == 'scheduled';
  bool get isFailed => status == 'failed';
  bool get isDrafting => status == 'drafting';
  bool get isCancelled => status == 'cancelled';
  bool get isPending => status == 'scheduled' || status == 'sending' || isDrafting;

  String previewText() {
    final trimmed = text.trim();
    if (trimmed.isNotEmpty) {
      return trimmed;
    }
    if (attachments.isNotEmpty) {
      final first = attachments.first;
      if (first.isImage) {
        return '📷 Photo';
      }
      return '📎 Attachment';
    }
    return '';
  }

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
}
