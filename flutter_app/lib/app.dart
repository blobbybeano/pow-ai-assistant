import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'models/app_user.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'services/auth_repository.dart';
import 'theme/app_theme.dart';

class PowWashApp extends StatelessWidget {
  const PowWashApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Provider<AuthService>(
      create: (_) => AuthService(),
      child: MaterialApp(
        title: 'PowWash Workspace',
        theme: buildPowWashTheme(),
        home: const _AuthGate(),
      ),
    );
  }
}

class _AuthGate extends StatelessWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context) {
    final authService = context.read<AuthService>();

    return StreamBuilder<AppUser?>(
      stream: authService.userChanges,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        final appUser = snapshot.data;
        if (appUser == null || FirebaseAuth.instance.currentUser == null) {
          return const AuthScreen();
        }

        return HomeScreen(user: appUser);
      },
    );
  }
}
