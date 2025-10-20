import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/inbox_controller.dart';
import '../controllers/user_controller.dart';
import '../models/app_user.dart';
import '../widgets/pending_ai_banner.dart';

class UserSelectionScreen extends StatefulWidget {
  const UserSelectionScreen({super.key});

  @override
  State<UserSelectionScreen> createState() => _UserSelectionScreenState();
}

class _UserSelectionScreenState extends State<UserSelectionScreen> {
  final Set<String> _dismissedPendingAi = <String>{};

  void _handleDismiss(String conversationId) {
    setState(() {
      _dismissedPendingAi.add(conversationId);
    });
  }

  @override
  Widget build(BuildContext context) {
    final userController = context.watch<UserController>();
    final inbox = context.watch<InboxController>();
    final users = userController.availableUsers;

    final pendingSummaries = inbox.pendingAiConversations
        .where((summary) => !_dismissedPendingAi.contains(summary.id))
        .toList();

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final activeIds = inbox.pendingAiConversations.map((summary) => summary.id).toSet();
      if (_dismissedPendingAi.any((id) => !activeIds.contains(id))) {
        setState(() {
          _dismissedPendingAi.removeWhere((id) => !activeIds.contains(id));
        });
      }
    });

    return Scaffold(
      backgroundColor: const Color(0xFF0B141A),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Choose a profile',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Color(0xFFE9EDEF),
                      fontSize: 24,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'Sign in with your PowWash workspace account. You can switch profiles at any time.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
                  ),
                  const SizedBox(height: 24),
                  if (pendingSummaries.isNotEmpty) ...[
                    ...pendingSummaries.map(
                      (summary) => Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: PendingAiBanner(
                          summary: summary,
                          onDismissed: () => _handleDismiss(summary.id),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  _AiResponderSelector(
                    users: users,
                    selectedUserId: userController.respondingUser?.id,
                    onChanged: userController.switchRespondingUser,
                  ),
                  const SizedBox(height: 24),
                  Flexible(
                    child: ListView.separated(
                      shrinkWrap: true,
                      itemBuilder: (context, index) {
                        final user = users[index];
                        final unread = inbox.isLoading
                            ? null
                            : userController.unreadEnquiriesFor(user, inbox.conversations);
                        return _UserCard(
                          user: user,
                          isActive: userController.isCurrentUser(user),
                          notificationCount: unread,
                          onTap: () => userController.signIn(user.id),
                        );
                      },
                      separatorBuilder: (_, __) => const SizedBox(height: 12),
                      itemCount: users.length,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _UserCard extends StatelessWidget {
  const _UserCard({
    required this.user,
    required this.onTap,
    required this.isActive,
    required this.notificationCount,
  });

  final AppUser user;
  final VoidCallback onTap;
  final bool isActive;
  final int? notificationCount;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Ink(
        decoration: BoxDecoration(
          color: const Color(0xFF111B21),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: isActive ? const Color(0xFF00A884) : const Color(0x33243038)),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        child: Row(
          children: [
            CircleAvatar(
              radius: 26,
              backgroundColor:
                  user.photoUrl != null ? Colors.transparent : const Color(0x33243038),
              foregroundColor: const Color(0xFFE9EDEF),
              backgroundImage:
                  user.photoUrl != null ? NetworkImage(user.photoUrl!) : null,
              child: user.photoUrl != null
                  ? null
                  : Text(
                      user.initials,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    user.displayName,
                    style: const TextStyle(
                      color: Color(0xFFE9EDEF),
                      fontWeight: FontWeight.w600,
                      fontSize: 16,
                    ),
                  ),
                  if (user.email != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      user.email!,
                      style: const TextStyle(color: Color(0xFF8696A0), fontSize: 13),
                    ),
                  ],
                  if ((notificationCount ?? 0) > 0) ...[
                    const SizedBox(height: 8),
                    _NotificationBadge(count: notificationCount!),
                  ],
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: Color(0xFF8696A0)),
          ],
        ),
      ),
    );
  }
}

class _NotificationBadge extends StatelessWidget {
  const _NotificationBadge({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFF1F2C34),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF00A884)),
      ),
      child: Text(
        count == 1 ? '1 new enquiry' : '$count new enquiries',
        style: const TextStyle(
          color: Color(0xFFE9EDEF),
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _AiResponderSelector extends StatelessWidget {
  const _AiResponderSelector({
    required this.users,
    required this.selectedUserId,
    required this.onChanged,
  });

  final List<AppUser> users;
  final String? selectedUserId;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF111B21),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE2B659), width: 1.5),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'AI responding as',
            style: TextStyle(
              color: Color(0xFFE9EDEF),
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Incoming enquiries will be answered on behalf of the selected user.',
            style: TextStyle(
              color: Color(0xFF8696A0),
              fontSize: 13,
              height: 1.4,
            ),
          ),
          const SizedBox(height: 12),
          DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: users.any((user) => user.id == selectedUserId)
                  ? selectedUserId
                  : null,
              icon: const Icon(Icons.keyboard_arrow_down, color: Color(0xFF8696A0)),
              dropdownColor: const Color(0xFF111B21),
              borderRadius: BorderRadius.circular(12),
              style: const TextStyle(color: Color(0xFFE9EDEF)),
              isExpanded: true,
              items: users
                  .map(
                    (user) => DropdownMenuItem<String>(
                      value: user.id,
                      child: Row(
                        children: [
                          CircleAvatar(
                            radius: 16,
                            backgroundColor: const Color(0x33243038),
                            foregroundColor: const Color(0xFFE9EDEF),
                            child: Text(
                              user.initials,
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  user.displayName,
                                  style: const TextStyle(
                                    color: Color(0xFFE9EDEF),
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                if (user.email != null)
                                  Text(
                                    user.email!,
                                    style: const TextStyle(
                                      color: Color(0xFF8696A0),
                                      fontSize: 12,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  )
                  .toList(),
              onChanged: (value) {
                if (value != null && value != selectedUserId) {
                  onChanged(value);
                }
              },
              hint: const Text(
                'Select a user',
                style: TextStyle(color: Color(0xFF8696A0)),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
