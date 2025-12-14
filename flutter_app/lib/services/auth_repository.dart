import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../models/app_user.dart';

class MemberProfile extends AppUser {
  const MemberProfile({
    required super.id,
    required super.displayName,
    required this.accountId,
    required this.role,
    super.email,
    super.avatarEmoji,
    super.photoUrl,
    super.assignedConversationIds,
  });

  final String accountId;
  final String role;

  MemberProfile copyWith({
    String? accountId,
    String? role,
    String? displayName,
    String? photoUrl,
  }) {
    return MemberProfile(
      id: id,
      displayName: displayName ?? this.displayName,
      email: email,
      avatarEmoji: avatarEmoji,
      photoUrl: photoUrl ?? this.photoUrl,
      assignedConversationIds: assignedConversationIds,
      accountId: accountId ?? this.accountId,
      role: role ?? this.role,
    );
  }
}

class AuthRepository {
  AuthRepository(
      {FirebaseAuth? auth, FirebaseFirestore? firestore, String? defaultAccountName})
      : _auth = auth ?? FirebaseAuth.instance,
        _firestore = firestore ?? FirebaseFirestore.instance,
        _defaultAccountName = defaultAccountName ?? 'PowWash Workspace';

  final FirebaseAuth _auth;
  final FirebaseFirestore _firestore;
  final String _defaultAccountName;

  Stream<User?> get authChanges => _auth.authStateChanges();

  Future<MemberProfile?> loadProfile(User? firebaseUser) async {
    if (firebaseUser == null) return null;

    final membership = await _firestore
        .collectionGroup('members')
        .where('userId', isEqualTo: firebaseUser.uid)
        .limit(1)
        .get();
    if (membership.docs.isEmpty) {
      return null;
    }

    final doc = membership.docs.first;
    final data = doc.data();
    final accountId = doc.reference.parent.parent?.id;
    if (accountId == null) return null;

    return MemberProfile(
      id: firebaseUser.uid,
      accountId: accountId,
      role: data['role'] as String? ?? 'staff',
      displayName: data['displayName'] as String? ?? firebaseUser.displayName ?? 'Agent',
      email: firebaseUser.email,
      photoUrl: data['photoUrl'] as String?,
      assignedConversationIds:
          (data['assignedConversationIds'] as List<dynamic>? ?? const <dynamic>[])
              .whereType<String>()
              .toList(),
    );
  }

  Future<MemberProfile> signUp({
    required String email,
    required String password,
    required String displayName,
  }) async {
    final credential = await _auth.createUserWithEmailAndPassword(
      email: email,
      password: password,
    );
    await credential.user?.updateDisplayName(displayName);
    return _createInitialAccount(credential.user!, displayName);
  }

  Future<MemberProfile> signIn({
    required String email,
    required String password,
  }) async {
    final credential = await _auth.signInWithEmailAndPassword(
      email: email,
      password: password,
    );
    final profile = await loadProfile(credential.user);
    if (profile != null) return profile;
    return _createInitialAccount(
      credential.user!,
      credential.user?.displayName ?? _defaultAccountName,
    );
  }

  Future<void> signOut() => _auth.signOut();

  Future<MemberProfile> _createInitialAccount(User user, String displayName) async {
    final accountRef = _firestore.collection('accounts').doc();
    final memberRef = accountRef.collection('members').doc(user.uid);
    final now = FieldValue.serverTimestamp();

    await _firestore.runTransaction((txn) async {
      txn.set(accountRef, {
        'name': _defaultAccountName,
        'createdAt': now,
        'ownerId': user.uid,
      });
      txn.set(memberRef, {
        'displayName': displayName,
        'userId': user.uid,
        'role': 'admin',
        'photoUrl': user.photoURL,
        'createdAt': now,
        'assignedConversationIds': <String>[],
      });
    });

    return MemberProfile(
      id: user.uid,
      displayName: displayName,
      email: user.email,
      photoUrl: user.photoURL,
      accountId: accountRef.id,
      role: 'admin',
      assignedConversationIds: const <String>[],
    );
  }
}
