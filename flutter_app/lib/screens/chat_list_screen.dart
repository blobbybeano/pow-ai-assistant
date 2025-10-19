import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/inbox_controller.dart';
import '../controllers/profile_controller.dart';
import '../controllers/user_controller.dart';
import '../models/conversation.dart';
import '../widgets/conversation_tile.dart';
import 'chat_detail_screen.dart';

class ChatListScreen extends StatelessWidget {
  const ChatListScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const _ChatListScaffold();
  }
}

class _ChatListScaffold extends StatelessWidget {
  const _ChatListScaffold();

  @override
  Widget build(BuildContext context) {
    return Consumer<InboxController>(
      builder: (context, inbox, _) {
        return Scaffold(
          backgroundColor: const Color(0xFF0B141A),
          appBar: AppBar(
            title: const Text('Chats'),
            backgroundColor: const Color(0xFF111B21),
            foregroundColor: const Color(0xFFE9EDEF),
            actions: [
              const _UserSwitcherButton(),
              IconButton(
                icon: const Icon(Icons.more_vert_rounded),
                onPressed: () => _showSettingsSheet(context, inbox.conversations),
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
              child: inbox.isLoading && inbox.conversations.isEmpty
                  ? const _LoadingState()
                  : inbox.error != null && inbox.conversations.isEmpty
                      ? _ErrorState(error: inbox.error!, onRetry: inbox.refresh)
                      : ListView.separated(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          itemCount: inbox.conversations.length,
                          separatorBuilder: (_, __) => const SizedBox(height: 12),
                          itemBuilder: (context, index) {
                            final summary = inbox.conversations[index];
                            return _ConversationListTile(summary: summary);
                          },
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
    final photoUrl = profileController.photoFor(summary.id);

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
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        Padding(
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
        )
      ],
    );
  }
}

void _showSettingsSheet(BuildContext context, List<ConversationSummary> conversations) {
  showModalBottomSheet(
    context: context,
    backgroundColor: const Color(0xFF111B21),
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (context) {
      return _ProfileSettingsSheet(conversations: conversations);
    },
  );
}

class _UserSwitcherButton extends StatelessWidget {
  const _UserSwitcherButton();

  @override
  Widget build(BuildContext context) {
    final userController = context.watch<UserController>();
    final currentUser = userController.currentUser;
    final users = userController.availableUsers;

    return PopupMenuButton<String>(
      tooltip: 'Switch profile',
      onSelected: (value) {
        if (value == '_logout') {
          userController.signOut();
        } else {
          userController.signIn(value);
        }
      },
      itemBuilder: (context) {
        return [
          for (final user in users)
            PopupMenuItem<String>(
              value: user.id,
              child: Row(
                children: [
                  if (userController.isCurrentUser(user))
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
          const PopupMenuDivider(),
          const PopupMenuItem<String>(
            value: '_logout',
            child: Text('Log out'),
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
            currentUser?.initials ?? '–',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
      ),
    );
  }
}

class _ProfileSettingsSheet extends StatefulWidget {
  const _ProfileSettingsSheet({required this.conversations});

  final List<ConversationSummary> conversations;

  @override
  State<_ProfileSettingsSheet> createState() => _ProfileSettingsSheetState();
}

class _ProfileSettingsSheetState extends State<_ProfileSettingsSheet> {
  final TextEditingController _urlController = TextEditingController();
  String? _selectedId;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_selectedId == null && widget.conversations.isNotEmpty) {
      _updateSelection(widget.conversations.first.id);
    }
  }

  void _updateSelection(String id) {
    final profileController = context.read<ProfileController>();
    final existing = profileController.photoFor(id);
    setState(() {
      _selectedId = id;
      _urlController.text = existing ?? '';
    });
  }

  @override
  Widget build(BuildContext context) {
    final profileController = context.watch<ProfileController>();

    if (widget.conversations.isEmpty) {
      return Padding(
        padding: MediaQuery.of(context).viewInsets + const EdgeInsets.all(24),
        child: const Text(
          'No chats available yet. Start a conversation to customise profile pictures.',
          style: TextStyle(color: Color(0xFFE9EDEF), fontSize: 16),
        ),
      );
    }

    final selectedConversation = widget.conversations.firstWhere(
      (conversation) => conversation.id == _selectedId,
      orElse: () => widget.conversations.first,
    );

    return Padding(
      padding: MediaQuery.of(context).viewInsets + const EdgeInsets.fromLTRB(24, 24, 24, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.settings, color: Color(0xFF00A884)),
              const SizedBox(width: 12),
              const Text(
                'Chat settings',
                style: TextStyle(
                  color: Color(0xFFE9EDEF),
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          DropdownButtonFormField<String>(
            value: selectedConversation.id,
            dropdownColor: const Color(0xFF111B21),
            decoration: const InputDecoration(
              labelText: 'Conversation',
            ),
            items: [
              for (final conversation in widget.conversations)
                DropdownMenuItem(
                  value: conversation.id,
                  child: Text(
                    conversation.displayName,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
            onChanged: (value) {
              if (value != null) {
                _updateSelection(value);
              }
            },
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _urlController,
            decoration: const InputDecoration(
              labelText: 'Profile picture URL',
              hintText: 'https://example.com/avatar.jpg',
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              ElevatedButton(
                onPressed: _selectedId == null
                    ? null
                    : () {
                        profileController.setPhoto(_selectedId!, _urlController.text);
                        Navigator.of(context).pop();
                      },
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00A884),
                  foregroundColor: Colors.white,
                ),
                child: const Text('Save'),
              ),
              const SizedBox(width: 12),
              TextButton(
                onPressed: _selectedId == null
                    ? null
                    : () {
                        profileController.setPhoto(_selectedId!, null);
                        Navigator.of(context).pop();
                      },
                child: const Text('Remove photo'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          const Text(
            'Tip: Paste an image URL to set the contact\'s avatar. Leave empty to use their initials.',
            style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
          ),
        ],
      ),
    );
  }
}
