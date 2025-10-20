import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/profile_controller.dart';
import '../models/conversation.dart';

Future<T?> showProfileSettingsSheet<T>(
  BuildContext context,
  List<ConversationSummary> conversations,
) {
  return showModalBottomSheet<T>(
    context: context,
    backgroundColor: const Color(0xFF111B21),
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (context) {
      return ProfileSettingsSheet(conversations: conversations);
    },
  );
}

class ProfileSettingsSheet extends StatefulWidget {
  const ProfileSettingsSheet({super.key, required this.conversations});

  final List<ConversationSummary> conversations;

  @override
  State<ProfileSettingsSheet> createState() => _ProfileSettingsSheetState();
}

class _ProfileSettingsSheetState extends State<ProfileSettingsSheet> {
  final TextEditingController _urlController = TextEditingController();
  String? _selectedId;

  @override
  void initState() {
    super.initState();
    if (widget.conversations.isNotEmpty) {
      _selectedId = widget.conversations.first.id;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_selectedId != null) {
      _syncExistingUrl(_selectedId!);
    }
  }

  @override
  void didUpdateWidget(covariant ProfileSettingsSheet oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.conversations.isEmpty) {
      _selectedId = null;
      _urlController.text = '';
      return;
    }
    if (_selectedId == null ||
        !widget.conversations.any((conversation) => conversation.id == _selectedId)) {
      _updateSelection(widget.conversations.first.id);
    }
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  void _syncExistingUrl(String id) {
    final profileController = context.read<ProfileController>();
    final existing = profileController.photoFor(id);
    _urlController.text = existing ?? '';
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
            children: const [
              Icon(Icons.settings, color: Color(0xFF00A884)),
              SizedBox(width: 12),
              Text(
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
