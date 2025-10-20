import 'message.dart';

class ConversationSummary {
  ConversationSummary({
    required this.id,
    required this.phoneNumber,
    required this.displayName,
    required this.aiEnabled,
    required this.unreadCount,
    this.profilePhotoUrl,
    this.lastMessage,
  });

  factory ConversationSummary.fromJson(Map<String, dynamic> json) {
    return ConversationSummary(
      id: json['id'] as String,
      phoneNumber: json['phoneNumber'] as String,
      displayName: json['displayName'] as String,
      aiEnabled: json['aiEnabled'] as bool? ?? true,
      unreadCount: json['unreadCount'] as int? ?? 0,
      profilePhotoUrl: json['profilePhotoUrl'] as String?,
      lastMessage: json['lastMessage'] != null
          ? ChatMessage.fromJson(json['lastMessage'] as Map<String, dynamic>)
          : null,
    );
  }

  final String id;
  final String phoneNumber;
  final String displayName;
  final bool aiEnabled;
  final int unreadCount;
  final String? profilePhotoUrl;
  final ChatMessage? lastMessage;
}

class ConversationDetail {
  ConversationDetail({
    required this.id,
    required this.phoneNumber,
    required this.displayName,
    required this.aiEnabled,
    required this.unreadCount,
    required this.messages,
    this.profilePhotoUrl,
  });

  factory ConversationDetail.fromJson(Map<String, dynamic> json) {
    final messagesJson = json['messages'] as List<dynamic>? ?? [];
    return ConversationDetail(
      id: json['id'] as String,
      phoneNumber: json['phoneNumber'] as String,
      displayName: json['displayName'] as String,
      aiEnabled: json['aiEnabled'] as bool? ?? true,
      unreadCount: json['unreadCount'] as int? ?? 0,
      messages: messagesJson
          .map((message) => ChatMessage.fromJson(message as Map<String, dynamic>))
          .toList(),
      profilePhotoUrl: json['profilePhotoUrl'] as String?,
    );
  }

  final String id;
  final String phoneNumber;
  final String displayName;
  final bool aiEnabled;
  final int unreadCount;
  final List<ChatMessage> messages;
  final String? profilePhotoUrl;
}
