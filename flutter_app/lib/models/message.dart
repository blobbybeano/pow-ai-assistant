import 'package:cloud_firestore/cloud_firestore.dart';
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
    this.scheduledSendAt,
    this.sentAt,
    this.transportSid,
    this.error,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> json) =>
      ChatMessage.fromMap(json);

  factory ChatMessage.fromMap(Map<String, dynamic> json) {
    DateTime? _parseDate(dynamic value) => _parseTimestamp(value)?.toLocal();
    return ChatMessage(
      id: json['id'] as String? ?? '',
      text: json['text'] as String? ?? '',
      author: json['author'] as String? ?? 'customer',
      direction: json['direction'] as String? ?? 'inbound',
      timestamp: _parseTimestamp(json['timestamp'])?.toLocal() ?? DateTime.now(),
      via: json['via'] as String? ?? 'whatsapp',
      status: json['status'] as String? ?? 'sent',
      attachments: _parseAttachments(
        json['attachments'] ?? json['media'],
      ),
      scheduledSendAt: _parseDate(json['scheduledSendAt']),
      sentAt: _parseDate(json['sentAt']),
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
  final List<String> attachments;
  final DateTime? scheduledSendAt;
  final DateTime? sentAt;
  final String? transportSid;
  final String? error;

  bool get isInbound => direction == 'inbound';

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
}

List<String> _parseAttachments(dynamic value) {
  if (value is! List) return const [];

  final paths = <String>[];
  for (final item in value) {
    if (item is String && item.isNotEmpty) {
      paths.add(item);
    } else if (item is Map<String, dynamic>) {
      final contentType = item['content_type'] ?? item['contentType'];
      final path = item['path'] ?? item['url'] ?? item['uri'];
      final isImageAttachment = contentType == null ||
          (contentType is String && contentType.toLowerCase().startsWith('image/'));

      if (isImageAttachment && path is String && path.isNotEmpty) {
        paths.add(path);
      }
    }
  }

  return paths;
}

DateTime? _parseTimestamp(dynamic value) {
  if (value is Timestamp) return value.toDate();
  if (value is DateTime) return value;
  if (value is String && value.isNotEmpty) return DateTime.parse(value);
  return null;
}
