import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../models/app_user.dart';
import '../models/conversation.dart';
import '../services/auth_repository.dart';

class UserController extends ChangeNotifier {
  UserController({
    required AuthRepository authRepository,
  })  : _authRepository = authRepository {
    _authSubscription = _authRepository.authChanges.listen(_handleAuthChange);
    _loadExistingSession();
  }

  final AuthRepository _authRepository;
  late final StreamSubscription<User?> _authSubscription;

  AppUser? _currentUser;
  bool _isLoading = true;
  Object? _error;

  AppUser? get currentUser => _currentUser;
  bool get isSignedIn => _currentUser != null;
  bool get isLoading => _isLoading;
  Object? get error => _error;

  List<AppUser> get availableUsers =>
      _currentUser == null ? const [] : <AppUser>[_currentUser!];

  AppUser? get respondingUser => _currentUser;

  Set<String> get _knownAssignedConversationIds =>
      _currentUser?.assignedConversationIds.toSet() ?? const <String>{};

  @override
  void dispose() {
    _authSubscription.cancel();
    super.dispose();
  }

  Future<void> signIn(String email, String password) async {
    _setLoading(true);
    try {
      _error = null;
      final member = await _authRepository.signIn(
        email: email,
        password: password,
      );
      _currentUser = member;
    } catch (err) {
      _error = err;
      rethrow;
    } finally {
      _setLoading(false);
    }
  }

  Future<void> signUp({
    required String email,
    required String password,
    required String displayName,
  }) async {
    _setLoading(true);
    try {
      _error = null;
      final member = await _authRepository.signUp(
        email: email,
        password: password,
        displayName: displayName,
      );
      _currentUser = member;
    } catch (err) {
      _error = err;
      rethrow;
    } finally {
      _setLoading(false);
    }
  }

  Future<void> signOut() async {
    await _authRepository.signOut();
    _currentUser = null;
    notifyListeners();
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
          final assignedResponder = conversation.assignedResponderId;
          if (assignedResponder != null && assignedResponder.isNotEmpty) {
            return assignedResponder == user.id;
          }
          if (assigned.contains(conversation.id)) {
            return true;
          }
          final isUnassignedLegacy = !knownAssignments.contains(conversation.id);
          return isUnassignedLegacy;
        })
        .toList();
  }

  int unreadEnquiriesFor(AppUser user, List<ConversationSummary> conversations) {
    return assignedConversations(conversations, forUser: user)
        .fold<int>(0, (total, conversation) => total + conversation.unreadCount);
  }

  void _setLoading(bool value) {
    if (_isLoading == value) return;
    _isLoading = value;
    notifyListeners();
  }

  Future<void> _handleAuthChange(User? firebaseUser) async {
    if (firebaseUser == null) {
      _currentUser = null;
      notifyListeners();
      return;
    }
    final profile = await _authRepository.loadProfile(firebaseUser);
    if (profile != null) {
      _currentUser = profile;
      notifyListeners();
    }
  }

  Future<void> _loadExistingSession() async {
    try {
      final member = await _authRepository.loadProfile(FirebaseAuth.instance.currentUser);
      _currentUser = member;
    } finally {
      _setLoading(false);
    }
  }
}
