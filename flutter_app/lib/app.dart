import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'controllers/inbox_controller.dart';
import 'controllers/profile_controller.dart';
import 'controllers/user_controller.dart';
import 'screens/chat_list_screen.dart';
import 'screens/user_selection_screen.dart';
import 'services/chat_api_client.dart';
import 'theme/app_theme.dart';

class PowWashApp extends StatefulWidget {
  const PowWashApp({super.key});

  @override
  State<PowWashApp> createState() => _PowWashAppState();
}

class _PowWashAppState extends State<PowWashApp> {
  late final ChatApiClient _apiClient;

  @override
  void initState() {
    super.initState();
    _apiClient = ChatApiClient.fromEnvironment();
  }

  @override
  void dispose() {
    _apiClient.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<ChatApiClient>.value(value: _apiClient),
        ChangeNotifierProvider(
          create: (context) => UserController(
            apiClient: context.read<ChatApiClient>(),
          ),
        ),
        ChangeNotifierProvider(
          create: (context) => InboxController(
            apiClient: context.read<ChatApiClient>(),
          ),
        ),
        ChangeNotifierProvider(create: (_) => ProfileController()),
      ],
      child: MaterialApp(
        title: 'PowWash Workspace',
        theme: buildPowWashTheme(),
        home: const _AppRouter(),
      ),
    );
  }
}

class _AppRouter extends StatelessWidget {
  const _AppRouter();

  @override
  Widget build(BuildContext context) {
    return Consumer<UserController>(
      builder: (context, users, _) {
        if (!users.isSignedIn) {
          return const UserSelectionScreen();
        }
        return const ChatListScreen();
      },
    );
  }
}
