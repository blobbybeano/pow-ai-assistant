import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'controllers/inbox_controller.dart';
import 'controllers/profile_controller.dart';
import 'controllers/user_controller.dart';
import 'screens/auth_screen.dart';
import 'screens/chat_list_screen.dart';
import 'services/auth_repository.dart';
import 'services/chat_api_client.dart';
import 'services/firestore_chat_repository.dart';
import 'theme/app_theme.dart';

class PowWashApp extends StatelessWidget {
  const PowWashApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<AuthRepository>(create: (_) => AuthRepository()),
        Provider<ChatApiClient>(
          create: (context) => ChatApiClient.fromEnvironment(
            tokenProvider: () => context.read<AuthRepository>().getIdToken(),
          ),
        ),
        Provider<FirestoreChatRepository>(create: (_) => FirestoreChatRepository()),
        ChangeNotifierProvider<UserController>(
          create: (context) => UserController(
            authRepository: context.read<AuthRepository>(),
          ),
        ),
        ChangeNotifierProxyProvider<UserController, InboxController>(
          create: (context) =>
              InboxController(chatRepository: context.read<FirestoreChatRepository>()),
          update: (context, userController, inbox) {
            final controller = inbox ??
                InboxController(chatRepository: context.read<FirestoreChatRepository>());
            controller.updateAccount(userController.currentUser?.accountId);
            return controller;
          },
        ),
        ChangeNotifierProvider<ProfileController>(
          create: (_) => ProfileController(),
        ),
      ],
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
    return Consumer<UserController>(
      builder: (context, users, _) {
        if (users.isLoading) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        final currentUser = users.currentUser;
        if (currentUser == null) {
          return const AuthScreen();
        }

        return const ChatListScreen();
      },
    );
  }
}
