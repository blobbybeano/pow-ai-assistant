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

  Future<void> signIn(String email, String password) {
    return _auth.signInWithEmailAndPassword(email: email, password: password);
  }

  Future<void> signUp(String email, String password) async {
    final credential = await _auth.createUserWithEmailAndPassword(
      email: email,
      password: password,
    );

    final uid = credential.user?.uid;
    final userEmail = credential.user?.email;
    if (uid == null || userEmail == null) {
      throw FirebaseAuthException(
        code: 'invalid-user',
        message: 'Unable to create account. Please try again.',
      );
    }

    await _firestore.collection('users').doc(uid).set({
      'uid': uid,
      'email': userEmail,
      'role': 'user',
      'createdAt': FieldValue.serverTimestamp(),
    });
  }

  Future<AppUser?> _loadUserProfile(User firebaseUser) async {
    final userDoc = await _firestore.collection('users').doc(firebaseUser.uid).get();
    final data = userDoc.data();
    final role = (data != null && data['role'] is String)
        ? data['role'] as String
        : 'user';
    final email = firebaseUser.email ?? '';
    if (email.isEmpty) return null;
    return AppUser(
      uid: firebaseUser.uid,
      email: email,
      role: role,
    );
  }

  Future<void> signOut() => _auth.signOut();
}
