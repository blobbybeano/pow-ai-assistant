import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/inbox_controller.dart';
import '../controllers/profile_controller.dart';
import '../controllers/user_controller.dart';
import '../models/conversation.dart';
import '../widgets/conversation_tile.dart';
import '../widgets/pending_ai_banner.dart';
import '../widgets/profile_settings_sheet.dart';
import 'ai_training_dashboard_screen.dart';
import 'chat_detail_screen.dart';
import 'integration_settings_screen.dart';

class ChatListScreen extends StatelessWidget {
  const ChatListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const _ChatListScaffold();
  }
}

class _ChatListScaffold extends StatefulWidget {
  const _ChatListScaffold();

  @override
  State<_ChatListScaffold> createState() => _ChatListScaffoldState();
}

class _ChatListScaffoldState extends State<_ChatListScaffold> {
  final Set<String> _dismissedPendingAi = <String>{};

  void _handleDismiss(String conversationId) {
    setState(() {
      _dismissedPendingAi.add(conversationId);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<InboxController>(
      builder: (context, inbox, _) {
        final userController = context.watch<UserController>();
        final visibleConversations =
            userController.assignedConversations(inbox.conversations);
        final pendingSummaries = userController
            .assignedConversations(inbox.pendingAiConversations)
            .where((summary) => !_dismissedPendingAi.contains(summary.id))
            .toList();

        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          final profileController = context.read<ProfileController>();
          for (final conversation in visibleConversations) {
            if (conversation.profilePhotoUrl != null) {
              profileController.setPhoto(conversation.id, conversation.profilePhotoUrl);
            }
          }
        });

        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted) return;
          final activeIds = userController
              .assignedConversations(inbox.pendingAiConversations)
              .map((summary) => summary.id)
              .toSet();
          if (_dismissedPendingAi.any((id) => !activeIds.contains(id))) {
            setState(() {
              _dismissedPendingAi.removeWhere((id) => !activeIds.contains(id));
            });
          }
        });

        final listChildren = <Widget>[];
        if (pendingSummaries.isNotEmpty) {
          for (final summary in pendingSummaries) {
            listChildren.add(
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: PendingAiBanner(
                  summary: summary,
                  responder: userController.respondingUser,
                  onDismissed: () => _handleDismiss(summary.id),
                ),
              ),
            );
          }
          listChildren.add(const SizedBox(height: 12));
        }

        if (inbox.isLoading && visibleConversations.isEmpty) {
          listChildren.add(const _LoadingState());
        } else if (inbox.error != null && visibleConversations.isEmpty) {
          listChildren.add(_ErrorState(error: inbox.error!, onRetry: inbox.refresh));
        } else if (!inbox.isLoading && visibleConversations.isEmpty) {
          listChildren.add(const _EmptyState());
        } else {
          for (var i = 0; i < visibleConversations.length; i++) {
            final summary = visibleConversations[i];
            listChildren.add(_ConversationListTile(summary: summary));
            if (i != visibleConversations.length - 1) {
              listChildren.add(const SizedBox(height: 12));
            }
          }
        }

        if (listChildren.isEmpty) {
          listChildren.add(const SizedBox(height: 80));
        }

        return Scaffold(
          backgroundColor: const Color(0xFF0B141A),
          appBar: AppBar(
            title: const Text('Chats'),
            backgroundColor: const Color(0xFF111B21),
            foregroundColor: const Color(0xFFE9EDEF),
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_rounded),
              tooltip: 'Switch account',
              onPressed: () => context.read<UserController>().signOut(),
            ),
            actions: [
              const _ResponderSwitcherButton(),
              IconButton(
                icon: const Icon(Icons.settings),
                onPressed: () async {
                  final action = await showProfileSettingsSheet(
                    context,
                    visibleConversations,
                  );
                  if (!mounted) return;
                  switch (action) {
                    case ProfileSettingsAction.aiTrainingDashboard:
                      if (!mounted) return;
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => AiTrainingDashboardScreen(
                            conversations: visibleConversations,
                          ),
                        ),
                      );
                      break;
                    case ProfileSettingsAction.integrationTokens:
                      if (!mounted) return;
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => const IntegrationSettingsScreen(),
                        ),
                      );
                      break;
                    case null:
                      break;
                  }
                },
                tooltip: 'Settings',
              ),
            ],
          ),
          body: RefreshIndicator(
            backgroundColor: const Color(0xFF111B21),
            color: const Color(0xFF00A884),
            onRefresh: inbox.refresh,
            child: Container(
              color: const Color(0xFF0B141A),
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                children: listChildren,
              ),
            ),
          ),
        );
      },
    );
  }
}

class _ConversationListTile extends StatelessWidget {
  const _ConversationListTile({required this.summary});

  final ConversationSummary summary;

  @override
  Widget build(BuildContext context) {
    final profileController = context.watch<ProfileController>();
    final fallbackPhoto = summary.profilePhotoUrl;
    final photoUrl = profileController.photoFor(summary.id) ?? fallbackPhoto;

    return ConversationTile(
      summary: summary,
      avatarImage: photoUrl != null ? NetworkImage(photoUrl) : null,
      onTap: () async {
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => ChatDetailScreen(summary: summary),
          ),
        );
      },
    );
  }
}

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.only(top: 120),
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation(Color(0xFF00A884)),
        ),
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.error, required this.onRetry});

  final Object error;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 80),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const Icon(Icons.wifi_off, size: 40, color: Color(0xFF8696A0)),
          const SizedBox(height: 12),
          const Text(
            'Unable to load chats',
            style: TextStyle(
              color: Color(0xFFE9EDEF),
              fontWeight: FontWeight.w600,
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '$error',
            textAlign: TextAlign.center,
            style: const TextStyle(color: Color(0xFF8696A0), height: 1.4),
          ),
          const SizedBox(height: 16),
          ElevatedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF00A884),
              foregroundColor: Colors.white,
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 120),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: const [
          Icon(Icons.person_search_outlined, size: 42, color: Color(0xFF8696A0)),
          SizedBox(height: 12),
          Text(
            'No assigned chats yet',
            style: TextStyle(
              color: Color(0xFFE9EDEF),
              fontWeight: FontWeight.w600,
              fontSize: 16,
            ),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: 8),
          Text(
            'When a customer thread is assigned to you, it will appear here automatically.',
            style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

class _ResponderSwitcherButton extends StatelessWidget {
  const _ResponderSwitcherButton();

  @override
  Widget build(BuildContext context) {
    final userController = context.watch<UserController>();
    final respondingUser = userController.respondingUser;
    final users = userController.availableUsers;

    if (users.isEmpty) {
      return const SizedBox.shrink();
    }

    final label = respondingUser != null
        ? 'AI responding as ${respondingUser.displayName}'
        : 'Select AI responder';

    return PopupMenuButton<AppUser>(
      tooltip: label,
      onSelected: userController.switchRespondingUser,
      itemBuilder: (context) {
        return [
          for (final user in users)
            PopupMenuItem<AppUser>(
              value: user,
              child: Row(
                children: [
                  if (userController.isRespondingUser(user))
                    const Icon(Icons.check, size: 18)
                  else
                    const SizedBox(width: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      user.displayName,
                      style: const TextStyle(fontWeight: FontWeight.w500),
                    ),
                  ),
                ],
              ),
            ),
        ];
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: CircleAvatar(
          radius: 16,
          backgroundColor: const Color(0x33243038),
          foregroundColor: const Color(0xFFE9EDEF),
          child: Text(
            respondingUser?.initials ?? 'AI',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
      ),
    );
  }
}
