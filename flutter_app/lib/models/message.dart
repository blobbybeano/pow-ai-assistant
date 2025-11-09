import 'package:intl/intl.dart';

class ChatAttachment {
  ChatAttachment({
    required this.id,
    required this.url,
    this.contentType,
    this.filename,
  });

  factory ChatAttachment.fromJson(Map<String, dynamic> json) {
    return ChatAttachment(
      id: json['id'] as String? ?? json['url'] as String? ?? '',
      url: json['url'] as String? ?? '',
      contentType: json['contentType'] as String?,
      filename: json['filename'] as String?,
    );
  }

  final String id;
  final String url;
  final String? contentType;
  final String? filename;

  bool get isImage => (contentType ?? '').startsWith('image/');

  String label() {
    if (isImage) {
      return 'Photo';
    }
    return 'Attachment';
  }
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
    this.scheduledSendAt,
    this.sentAt,
    this.transportSid,
    this.error,
    this.attachments = const [],
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    DateTime? _parseDate(String? value) =>
        value != null ? DateTime.parse(value).toLocal() : null;
    final attachmentsJson = json['attachments'] as List<dynamic>? ?? const [];
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
      attachments: attachmentsJson
          .map((value) => ChatAttachment.fromJson(value as Map<String, dynamic>))
          .where((attachment) => attachment.url.isNotEmpty)
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
  final DateTime? scheduledSendAt;
  final DateTime? sentAt;
  final String? transportSid;
  final String? error;
  final List<ChatAttachment> attachments;

  bool get isInbound => direction == 'inbound';

  DateTime get displayTimestamp => sentAt ?? scheduledSendAt ?? timestamp;

  String formattedTime() => DateFormat.jm().format(displayTimestamp);

  bool get hasAttachments => attachments.isNotEmpty;
  bool get isScheduled => status == 'scheduled';
  bool get isFailed => status == 'failed';
  bool get isDrafting => status == 'drafting';
  bool get isCancelled => status == 'cancelled';
  bool get isPending => status == 'scheduled' || status == 'sending' || isDrafting;

  String summaryText() {
    if (text.trim().isNotEmpty) {
      return text;
    }
    if (attachments.isEmpty) {
      return '';
    }
    final photoCount = attachments.where((attachment) => attachment.isImage).length;
    if (photoCount > 0) {
      return photoCount == 1 ? '📷 Photo' : '📷 $photoCount photos';
    }
    final attachmentCount = attachments.length;
    return attachmentCount == 1
        ? '📎 Attachment'
        : '📎 $attachmentCount attachments';
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
