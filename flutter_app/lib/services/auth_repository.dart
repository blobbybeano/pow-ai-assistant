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

  Future<void> signIn({
    required String email,
    required String password,
  }) {
    return _auth.signInWithEmailAndPassword(
      email: email,
      password: password,
    );
  }

  Future<void> signUp({
    required String email,
    required String password,
  }) async {
    final credential = await _auth.createUserWithEmailAndPassword(
      email: email,
      password: password,
    );
    final user = credential.user;
    if (user != null) {
      await _createUserDocument(user, fallbackEmail: email);
    }
  }

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

  Future<AppUser?> _loadUserProfile(User firebaseUser) async {
    final userDoc = await _firestore.collection('users').doc(firebaseUser.uid).get();
    if (!userDoc.exists) {
      await _createUserDocument(firebaseUser, fallbackEmail: firebaseUser.email ?? '');
    }
    final data = userDoc.data();
    final roleValue = data?['role'];
    final role = (roleValue is String && roleValue.isNotEmpty) ? roleValue : 'user';
    final email = firebaseUser.email ?? '';
    if (email.isEmpty) return null;
    return AppUser(
      uid: firebaseUser.uid,
      email: email,
      role: role,
    );
  }

  Future<void> _createUserDocument(
    User user, {
    required String fallbackEmail,
  }) async {
    final email = user.email ?? fallbackEmail;
    if (email.isEmpty) return;
    final usersRef = _firestore.collection('users').doc(user.uid);
    await usersRef.set({
      'uid': user.uid,
      'email': email,
      'role': 'user',
      'createdAt': FieldValue.serverTimestamp(),
    });
  }

  Future<void> signOut() => _auth.signOut();
}
