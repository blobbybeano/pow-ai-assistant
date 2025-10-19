import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'controllers/inbox_controller.dart';
import 'screens/workspace_screen.dart';
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
        ChangeNotifierProvider(create: (_) => InboxController(apiClient: _apiClient)),
      ],
      child: MaterialApp(
        title: 'PowWash Workspace',
        theme: buildPowWashTheme(),
        home: const WorkspaceScreen(),
      ),
    );
  }
}
