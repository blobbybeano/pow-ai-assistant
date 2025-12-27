import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../models/app_user.dart';

class AuthRepository {
  AuthRepository({
    FirebaseAuth? auth,
    FirebaseFirestore? firestore,
  })  : _auth = auth ?? FirebaseAuth.instance,
        _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseAuth _auth;
  final FirebaseFirestore _firestore;

  Stream<User?> get authChanges => _auth.authStateChanges();

  Stream<AppUser?> get userChanges async* {
    await for (final firebaseUser in authChanges) {
      yield await loadProfile(firebaseUser);
    }
  }

  Future<AppUser> signIn({
    required String email,
    required String password,
  }) async {
    final credential = await _auth.signInWithEmailAndPassword(
      email: email,
      password: password,
    );
    final firebaseUser = credential.user;
    if (firebaseUser == null) {
      throw FirebaseAuthException(code: 'user-not-found');
    }
    return _ensureMembership(firebaseUser, fallbackEmail: email);
  }

  Future<AppUser> signUp({
    required String email,
    required String password,
    required String displayName,
  }) async {
    final credential = await _auth.createUserWithEmailAndPassword(
      email: email,
      password: password,
    );
    final firebaseUser = credential.user;
    if (firebaseUser == null) {
      throw FirebaseAuthException(code: 'user-not-found');
    }

    await firebaseUser.updateDisplayName(displayName);
    return _createMembership(
      firebaseUser,
      displayName: displayName,
      email: email,
    );
  }

  Future<AppUser?> loadProfile(User? firebaseUser) async {
    if (firebaseUser == null) return null;
    final membership = await _lookupMembership(firebaseUser.uid);
    if (membership != null) {
      return membership;
    }
    final displayName = firebaseUser.displayName ?? _deriveName(firebaseUser.email ?? '');
    return _createMembership(
      firebaseUser,
      displayName: displayName,
      email: firebaseUser.email ?? '',
    );
  }

  Future<void> signOut() => _auth.signOut();

  Future<String?> getIdToken() => _auth.currentUser?.getIdToken();

  Future<AppUser> _ensureMembership(
    User firebaseUser, {
    required String fallbackEmail,
  }) async {
    final membership = await _lookupMembership(firebaseUser.uid);
    if (membership != null) {
      return membership;
    }
    final displayName =
        firebaseUser.displayName ?? _deriveName(firebaseUser.email ?? fallbackEmail);
    return _createMembership(
      firebaseUser,
      displayName: displayName,
      email: firebaseUser.email ?? fallbackEmail,
    );
  }

  Future<AppUser?> _lookupMembership(String uid) async {
    final query = await _firestore
        .collectionGroup('members')
        .where('userId', isEqualTo: uid)
        .limit(1)
        .get();
    if (query.docs.isEmpty) return null;
    final membership = query.docs.first;
    final accountId = membership.reference.parent.parent?.id;
    if (accountId == null) return null;
    return AppUser.fromFirestore(membership, accountId: accountId);
  }

  Future<AppUser> _createMembership(
    User firebaseUser, {
    required String displayName,
    required String email,
  }) async {
    final preferredAccountId =
        const String.fromEnvironment('DEFAULT_ACCOUNT_ID', defaultValue: '');
    final accountId =
        preferredAccountId.isNotEmpty ? preferredAccountId : firebaseUser.uid;
    final accountRef = _firestore.collection('accounts').doc(accountId);
    final memberRef = accountRef.collection('members').doc(firebaseUser.uid);

    await accountRef.set({
      'name': '$displayName workspace',
      'ownerId': firebaseUser.uid,
      'createdAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));

    await memberRef.set({
      'userId': firebaseUser.uid,
      'displayName': displayName,
      'email': email,
      'photoUrl': firebaseUser.photoURL,
      'role': 'admin',
      'assignedConversationIds': <String>[],
      'createdAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));

    return AppUser(
      id: firebaseUser.uid,
      accountId: accountId,
      displayName: displayName,
      email: email,
      photoUrl: firebaseUser.photoURL,
      role: 'admin',
      assignedConversationIds: const <String>[],
    );
  }

  String _deriveName(String email) {
    if (email.isEmpty) return 'Workspace user';
    final localPart = email.split('@').first;
    final cleaned = localPart.replaceAll(RegExp(r'[._]+'), ' ').trim();
    if (cleaned.isEmpty) return 'Workspace user';
    final words = cleaned.split(RegExp(r'\s+')).where((word) => word.isNotEmpty);
    final capitalized = words
        .map((word) => word[0].toUpperCase() + word.substring(1))
        .join(' ')
        .trim();
    return capitalized.isEmpty ? 'Workspace user' : capitalized;
  }
}
