import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../models/app_user.dart';

class AuthService {
  AuthService({
    FirebaseAuth? auth,
    FirebaseFirestore? firestore,
  })  : _auth = auth ?? FirebaseAuth.instance,
        _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseAuth _auth;
  final FirebaseFirestore _firestore;

  Stream<User?> get authChanges => _auth.authStateChanges();

  Stream<AppUser?> get userChanges async* {
    await for (final firebaseUser in authChanges) {
      if (firebaseUser == null) {
        yield null;
        continue;
      }
      final profile = await _loadUserProfile(firebaseUser);
      yield profile;
    }
  }

  Future<void> signInWithEmailAndPassword({
    required String email,
    required String password,
  }) {
    return _auth.signInWithEmailAndPassword(
      email: email,
      password: password,
    );
  }

  Future<void> signUpWithEmailAndPassword({
    required String email,
    required String password,
  }) async {
    final credentials = await _auth.createUserWithEmailAndPassword(
      email: email,
      password: password,
    );

    final firebaseUser = credentials.user;
    if (firebaseUser == null) {
      throw FirebaseAuthException(
        code: 'user-creation-failed',
        message: 'Unable to create account.',
      );
    }

    await _firestore.collection('users').doc(firebaseUser.uid).set({
      'uid': firebaseUser.uid,
      'email': email,
      'role': 'user',
      'createdAt': FieldValue.serverTimestamp(),
    });
  }

  Future<AppUser?> _loadUserProfile(User firebaseUser) async {
    final email = firebaseUser.email ?? '';
    if (email.isEmpty) return null;

    try {
      final userDoc =
          await _firestore.collection('users').doc(firebaseUser.uid).get();
      final data = userDoc.data();
      final role = (data != null && data['role'] is String &&
              (data['role'] as String).isNotEmpty)
          ? data['role'] as String
          : 'user';

      return AppUser(
        uid: firebaseUser.uid,
        email: email,
        role: role,
      );
    } catch (_) {
      return AppUser(
        uid: firebaseUser.uid,
        email: email,
        role: 'user',
      );
    }
  }

  Future<void> signOut() => _auth.signOut();
}
