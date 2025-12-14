import 'package:flutter/foundation.dart';

class AppUser {
  const AppUser({
    required this.id,
    required this.displayName,
    this.email,
    this.accountId,
    this.role,
    this.avatarEmoji,
    this.photoUrl,
    this.assignedConversationIds = const <String>[],
  });

  final String id;
  final String displayName;
  final String? email;
  final String? accountId;
  final String? role;
  final String? avatarEmoji;
  final String? photoUrl;
  final List<String> assignedConversationIds;

  String get initials {
    if (avatarEmoji != null && avatarEmoji!.isNotEmpty) {
      return avatarEmoji!;
    }
    final cleaned = displayName.trim();
    if (cleaned.isEmpty) {
      return '?';
    }
    final parts = cleaned.split(RegExp(r'\s+')).where((part) => part.isNotEmpty).toList();
    String leading(String value) => value.isEmpty ? '' : value[0].toUpperCase();
    if (parts.length == 1) {
      return leading(parts.first);
    }
    return (leading(parts.first) + leading(parts.last)).trim();
  }

  AppUser copyWith({
    String? id,
    String? displayName,
    String? email,
    String? accountId,
    String? role,
    String? avatarEmoji,
    String? photoUrl,
    List<String>? assignedConversationIds,
  }) {
    return AppUser(
      id: id ?? this.id,
      displayName: displayName ?? this.displayName,
      email: email ?? this.email,
      accountId: accountId ?? this.accountId,
      role: role ?? this.role,
      avatarEmoji: avatarEmoji ?? this.avatarEmoji,
      photoUrl: photoUrl ?? this.photoUrl,
      assignedConversationIds:
          assignedConversationIds ?? this.assignedConversationIds,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is AppUser &&
        other.id == id &&
        other.displayName == displayName &&
        other.email == email &&
        other.avatarEmoji == avatarEmoji &&
        other.photoUrl == photoUrl &&
        listEquals(other.assignedConversationIds, assignedConversationIds);
  }

  @override
  int get hashCode => Object.hash(
        id,
        displayName,
        email,
        accountId,
        role,
        avatarEmoji,
        photoUrl,
        Object.hashAll(assignedConversationIds),
      );
}
