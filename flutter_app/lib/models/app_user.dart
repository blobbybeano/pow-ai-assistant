import 'package:cloud_firestore/cloud_firestore.dart';

class AppUser {
  const AppUser({
    required this.id,
    required this.accountId,
    required this.displayName,
    required this.email,
    required this.role,
    this.photoUrl,
    this.assignedConversationIds = const <String>[],
  });

  factory AppUser.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc, {
    required String accountId,
  }) {
    final data = doc.data() ?? <String, dynamic>{};
    final assigned = data['assignedConversationIds'];
    return AppUser(
      id: doc.id,
      accountId: accountId,
      displayName: (data['displayName'] as String? ?? '').trim(),
      email: (data['email'] as String? ?? '').trim(),
      role: (data['role'] as String? ?? 'staff').trim(),
      photoUrl: (data['photoUrl'] as String?)?.trim(),
      assignedConversationIds: assigned is Iterable
          ? List<String>.from(assigned.whereType<String>())
          : const <String>[],
    );
  }

  final String id;
  final String accountId;
  final String displayName;
  final String email;
  final String role;
  final String? photoUrl;
  final List<String> assignedConversationIds;

  String get initials {
    if (displayName.trim().isNotEmpty) {
      final parts = displayName.trim().split(RegExp(r'\s+'));
      final first = parts.first;
      final last = parts.length > 1 ? parts.last : '';
      return '${first.isNotEmpty ? first[0] : ''}${last.isNotEmpty ? last[0] : ''}'.toUpperCase();
    }
    if (email.trim().isNotEmpty) {
      final localPart = email.split('@').first;
      if (localPart.length >= 2) {
        return localPart.substring(0, 2).toUpperCase();
      }
      if (localPart.isNotEmpty) {
        return localPart[0].toUpperCase();
      }
    }
    return 'PW';
  }
}
