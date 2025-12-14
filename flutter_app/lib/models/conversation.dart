import 'package:cloud_firestore/cloud_firestore.dart';

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
    this.assignedResponderId,
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
      assignedResponderId: json['assignedResponderId'] as String?,
    );
  }

  final String id;
  final String phoneNumber;
  final String displayName;
  final bool aiEnabled;
  final int unreadCount;
  final String? profilePhotoUrl;
  final ChatMessage? lastMessage;
  final String? assignedResponderId;

  factory ConversationSummary.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? <String, dynamic>{};
    final lastMessageJson = data['lastMessage'] as Map<String, dynamic>?;
    return ConversationSummary(
      id: doc.id,
      phoneNumber: data['phoneNumber'] as String? ?? doc.id,
      displayName: data['displayName'] as String? ?? doc.id,
      aiEnabled: data['aiEnabled'] as bool? ?? true,
      unreadCount: (data['unreadCount'] as int?) ?? 0,
      profilePhotoUrl: data['profilePhotoUrl'] as String?,
      lastMessage: lastMessageJson != null
          ? ChatMessage.fromMap({...lastMessageJson, 'id': lastMessageJson['id'] ?? 'last-${doc.id}'})
          : null,
      assignedResponderId: data['assignedResponderId'] as String?,
    );
  }
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
    this.assignedResponderId,
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
      assignedResponderId: json['assignedResponderId'] as String?,
    );
  }

  final String id;
  final String phoneNumber;
  final String displayName;
  final bool aiEnabled;
  final int unreadCount;
  final List<ChatMessage> messages;
  final String? profilePhotoUrl;
  final String? assignedResponderId;

  factory ConversationDetail.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc, {
    required List<ChatMessage> messages,
  }) {
    final data = doc.data() ?? <String, dynamic>{};
    return ConversationDetail(
      id: doc.id,
      phoneNumber: data['phoneNumber'] as String? ?? doc.id,
      displayName: data['displayName'] as String? ?? doc.id,
      aiEnabled: data['aiEnabled'] as bool? ?? true,
      unreadCount: (data['unreadCount'] as int?) ?? 0,
      messages: messages,
      profilePhotoUrl: data['profilePhotoUrl'] as String?,
      assignedResponderId: data['assignedResponderId'] as String?,
    );
  }
}
