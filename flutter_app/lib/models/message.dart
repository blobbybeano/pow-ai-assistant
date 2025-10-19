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
        return 'Agent is typing…';
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
