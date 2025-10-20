import 'package:flutter/foundation.dart';

import '../models/app_user.dart';
import '../models/conversation.dart';

class UserController extends ChangeNotifier {
  UserController({List<AppUser>? availableUsers})
      : _availableUsers = availableUsers ?? _defaultUsers,
        _currentUserId = null,
        _respondingUserId = null;

  static final List<AppUser> _defaultUsers = [
    const AppUser(
      id: 'user-1',
      displayName: 'Alex Johnson',
      email: 'alex@example.com',
      photoUrl: 'https://i.pravatar.cc/160?img=32',
      assignedConversationIds: ['+15551230001'],
    ),
    const AppUser(
      id: 'user-2',
      displayName: 'Blake Rivera',
      email: 'blake@example.com',
      photoUrl: 'https://i.pravatar.cc/160?img=12',
      assignedConversationIds: ['+14085550100'],
    ),
    const AppUser(
      id: 'user-3',
      displayName: 'Casey Morgan',
      email: 'casey@example.com',
      photoUrl: 'https://i.pravatar.cc/160?img=45',
      assignedConversationIds: ['+447700900123'],
    ),
    const AppUser(
      id: 'user-4',
      displayName: 'Devin Patel',
      email: 'devin@example.com',
      photoUrl: 'https://i.pravatar.cc/160?img=18',
      assignedConversationIds: ['+16175550123'],
    ),
  ];

  final List<AppUser> _availableUsers;
  String? _currentUserId;
  String? _respondingUserId;

  Set<String> get _knownAssignedConversationIds => _availableUsers
      .expand((user) => user.assignedConversationIds)
      .where((id) => id.isNotEmpty)
      .toSet();

  List<AppUser> get availableUsers => List.unmodifiable(_availableUsers);

  AppUser? get currentUser {
    if (_currentUserId == null) return null;
    try {
      return _availableUsers.firstWhere((user) => user.id == _currentUserId);
    } catch (_) {
      return null;
    }
  }

  AppUser? get respondingUser {
    final explicitResponder = _respondingUserId;
    if (explicitResponder != null) {
      try {
        return _availableUsers.firstWhere((user) => user.id == explicitResponder);
      } catch (_) {
        // fall through to current user
      }
    }
    return currentUser;
  }

  bool get isSignedIn => _currentUserId != null;

  void signIn(String userId) {
    if (!_availableUsers.any((user) => user.id == userId)) return;
    final previousUser = _currentUserId;
    _currentUserId = userId;
    if (_respondingUserId == null || previousUser == null) {
      _respondingUserId ??= userId;
    }
    notifyListeners();
  }

  void signOut() {
    if (_currentUserId == null) return;
    _currentUserId = null;
    notifyListeners();
  }

  void switchRespondingUser(String userId) {
    if (_respondingUserId == userId) {
      return;
    }
    if (!_availableUsers.any((user) => user.id == userId)) {
      return;
    }
    _respondingUserId = userId;
    notifyListeners();
  }

  bool isCurrentUser(AppUser user) => user.id == _currentUserId;

  bool isRespondingUser(AppUser user) {
    final responder = respondingUser;
    return responder != null && responder.id == user.id;
  }

  List<ConversationSummary> assignedConversations(
    List<ConversationSummary> conversations, {
    AppUser? forUser,
  }) {
    final user = forUser ?? currentUser;
    if (user == null) {
      return const <ConversationSummary>[];
    }
    final assigned = user.assignedConversationIds.toSet();
    final knownAssignments = _knownAssignedConversationIds;
    return conversations
        .where((conversation) {
          if (assigned.contains(conversation.id)) {
            return true;
          }
          final isUnassigned = !knownAssignments.contains(conversation.id);
          return isUnassigned;
        })
        .toList();
  }

  int unreadEnquiriesFor(AppUser user, List<ConversationSummary> conversations) {
    return assignedConversations(conversations, forUser: user)
        .fold<int>(0, (total, conversation) => total + conversation.unreadCount);
  }
}
