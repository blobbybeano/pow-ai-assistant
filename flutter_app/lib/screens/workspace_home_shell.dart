import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/inbox_controller.dart';
import '../controllers/quote_request_controller.dart';
import '../controllers/user_controller.dart';
import '../models/app_user.dart';
import '../models/conversation.dart';
import '../widgets/pending_ai_banner.dart';
import 'chat_list_screen.dart';
import 'integration_settings_screen.dart';
import 'quote_requests_screen.dart';

class WorkspaceHomeShell extends StatefulWidget {
  const WorkspaceHomeShell({super.key});

  @override
  State<WorkspaceHomeShell> createState() => _WorkspaceHomeShellState();
}

class _WorkspaceHomeShellState extends State<WorkspaceHomeShell> {
  int _currentIndex = 0;

  void _selectTab(int index) {
    if (_currentIndex == index) return;
    setState(() {
      _currentIndex = index;
    });
  }

  @override
  Widget build(BuildContext context) {
    final pendingCount =
        context.watch<QuoteRequestController>().pendingCount;

    final pages = <Widget>[
      OverviewScreen(
        onOpenChats: () => _selectTab(1),
        onOpenIntegrationSettings: () => _selectTab(2),
        onOpenQuotes: () => _selectTab(3),
      ),
      const ChatListScreen(),
      const IntegrationSettingsScreen(),
      const QuoteRequestsScreen(),
    ];

    return Scaffold(
      backgroundColor: const Color(0xFF0B141A),
      appBar: _currentIndex == 0 ? const _TopAppBar() : null,
      body: IndexedStack(
        index: _currentIndex,
        children: pages,
      ),
      bottomNavigationBar: NavigationBar(
        backgroundColor: const Color(0xFF111B21),
        indicatorColor: const Color(0x331FDD94),
        selectedIndex: _currentIndex,
        labelBehavior: NavigationDestinationLabelBehavior.onlyShowSelected,
        onDestinationSelected: _selectTab,
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Workspace',
          ),
          const NavigationDestination(
            icon: Icon(Icons.chat_bubble_outline_rounded),
            selectedIcon: Icon(Icons.chat_bubble_rounded),
            label: 'Conversations',
          ),
          const NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: 'Settings',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: pendingCount > 0,
              label: Text('$pendingCount'),
              backgroundColor: const Color(0xFFF59E0B),
              textColor: Colors.black,
              child: const Icon(Icons.request_quote_outlined),
            ),
            selectedIcon: Badge(
              isLabelVisible: pendingCount > 0,
              label: Text('$pendingCount'),
              backgroundColor: const Color(0xFFF59E0B),
              textColor: Colors.black,
              child: const Icon(Icons.request_quote_rounded),
            ),
            label: 'Quotes',
          ),
        ],
      ),
    );
  }
}

class _TopAppBar extends StatelessWidget implements PreferredSizeWidget {
  const _TopAppBar();

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    return AppBar(
      backgroundColor: const Color(0xFF111B21),
      foregroundColor: const Color(0xFFE9EDEF),
      title: const Text('PowWash Workspace'),
      actions: [
        IconButton(
          icon: const Icon(Icons.logout_rounded),
          tooltip: 'Sign out',
          onPressed: () => context.read<UserController>().signOut(),
        ),
      ],
    );
  }
}

class OverviewScreen extends StatelessWidget {
  const OverviewScreen({
    super.key,
    required this.onOpenChats,
    required this.onOpenIntegrationSettings,
    required this.onOpenQuotes,
  });

  final VoidCallback onOpenChats;
  final VoidCallback onOpenIntegrationSettings;
  final VoidCallback onOpenQuotes;

  @override
  Widget build(BuildContext context) {
    final userController = context.watch<UserController>();
    final inboxController = context.watch<InboxController>();
    final quoteController = context.watch<QuoteRequestController>();
    final currentUser = userController.currentUser;
    final respondingUser = userController.respondingUser;
    final pendingSummaries = userController
        .assignedConversations(
          inboxController.pendingAiConversations,
          forUser: respondingUser,
        )
        .take(3)
        .toList();

    return SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const SizedBox(height: 4),
          const Text(
            'Workspace overview',
            style: TextStyle(
              color: Color(0xFFE9EDEF),
              fontSize: 22,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Quickly check who the AI is responding as and jump into conversations or integration settings.',
            style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
          ),
          const SizedBox(height: 24),
          if (quoteController.pendingCount > 0) ...[
            _QuoteBanner(
              count: quoteController.pendingCount,
              onTap: onOpenQuotes,
            ),
            const SizedBox(height: 16),
          ],
          if (pendingSummaries.isNotEmpty) ...[
            _PendingBannerDeck(
              summaries: pendingSummaries,
              responder: respondingUser,
            ),
            const SizedBox(height: 16),
          ],
          _UserCard(
            user: currentUser,
            respondingUser: respondingUser,
            onChangeResponder: userController.switchRespondingUser,
          ),
          const SizedBox(height: 16),
          _ActionRow(
            onOpenChats: onOpenChats,
            onOpenIntegrationSettings: onOpenIntegrationSettings,
          ),
        ],
      ),
    );
  }
}

class _QuoteBanner extends StatelessWidget {
  const _QuoteBanner({required this.count, required this.onTap});
  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: const Color(0xFFF59E0B).withOpacity(0.12),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFF59E0B).withOpacity(0.4)),
        ),
        child: Row(
          children: [
            const Icon(Icons.request_quote_rounded,
                color: Color(0xFFF59E0B), size: 22),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                '$count custom quote ${count == 1 ? 'request' : 'requests'} waiting for your advice',
                style: const TextStyle(
                  color: Color(0xFFF59E0B),
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
              ),
            ),
            const Icon(Icons.chevron_right_rounded,
                color: Color(0xFFF59E0B), size: 20),
          ],
        ),
      ),
    );
  }
}

class _UserCard extends StatelessWidget {
  const _UserCard({
    required this.user,
    required this.respondingUser,
    required this.onChangeResponder,
  });

  final AppUser? user;
  final AppUser? respondingUser;
  final ValueChanged<AppUser> onChangeResponder;

  @override
  Widget build(BuildContext context) {
    final users = context.watch<UserController>().availableUsers;
    final resolvedResponder = _resolveResponder(respondingUser, users);

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF111B21),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0x33243038)),
      ),
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 24,
                backgroundColor: const Color(0x33243038),
                foregroundColor: const Color(0xFFE9EDEF),
                child: Text(
                  (user?.initials ?? 'PW').toUpperCase(),
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      user?.displayName ?? 'Workspace user',
                      style: const TextStyle(
                        color: Color(0xFFE9EDEF),
                        fontWeight: FontWeight.w700,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      user?.email ?? 'Signed in',
                      style: const TextStyle(color: Color(0xFF8696A0)),
                    ),
                    if (user?.role != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        'Role: ${user!.role}',
                        style: const TextStyle(color: Color(0xFF8696A0)),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          const Text(
            'AI responds as',
            style: TextStyle(
              color: Color(0xFFE9EDEF),
              fontWeight: FontWeight.w600,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 8),
          DropdownButtonHideUnderline(
            child: DropdownButton<AppUser>(
              value: resolvedResponder ?? (users.isNotEmpty ? users.first : null),
              icon: const Icon(Icons.expand_more, color: Color(0xFF8696A0)),
              dropdownColor: const Color(0xFF111B21),
              borderRadius: BorderRadius.circular(12),
              isExpanded: true,
              style: const TextStyle(color: Color(0xFFE9EDEF)),
              items: users
                  .map(
                    (entry) => DropdownMenuItem<AppUser>(
                      value: entry,
                      child: Row(
                        children: [
                          CircleAvatar(
                            radius: 16,
                            backgroundColor: const Color(0x33243038),
                            foregroundColor: const Color(0xFFE9EDEF),
                            child: Text(
                              entry.initials,
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                entry.displayName,
                                style: const TextStyle(
                                  color: Color(0xFFE9EDEF),
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              if (entry.email != null)
                                Text(
                                  entry.email!,
                                  style: const TextStyle(
                                    color: Color(0xFF8696A0),
                                    fontSize: 12,
                                  ),
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  )
                  .toList(),
              onChanged: (value) {
                if (value != null) {
                  onChangeResponder(value);
                }
              },
              hint: const Text(
                'Select a responder',
                style: TextStyle(color: Color(0xFF8696A0)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  AppUser? _resolveResponder(AppUser? selected, List<AppUser> users) {
    if (selected == null) return null;
    for (final user in users) {
      if (user.id == selected.id) {
        return user;
      }
    }
    return null;
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.onOpenChats,
    required this.onOpenIntegrationSettings,
  });

  final VoidCallback onOpenChats;
  final VoidCallback onOpenIntegrationSettings;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: ElevatedButton.icon(
            onPressed: onOpenChats,
            icon: const Icon(Icons.forum_rounded),
            label: const Text('Open conversations'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF00A884),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: OutlinedButton.icon(
            onPressed: onOpenIntegrationSettings,
            icon: const Icon(Icons.settings_applications_rounded),
            label: const Text('Integration settings'),
            style: OutlinedButton.styleFrom(
              foregroundColor: const Color(0xFFE9EDEF),
              side: const BorderSide(color: Color(0xFF243038)),
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
          ),
        ),
      ],
    );
  }
}

class _PendingBannerDeck extends StatelessWidget {
  const _PendingBannerDeck({
    required this.summaries,
    required this.responder,
  });

  final List<ConversationSummary> summaries;
  final AppUser? responder;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Awaiting AI responses',
          style: TextStyle(
            color: Color(0xFFE9EDEF),
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        ...summaries.map(
          (summary) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: PendingAiBanner(
              summary: summary,
              responder: responder,
              onDismissed: () {},
            ),
          ),
        ),
      ],
    );
  }
}
