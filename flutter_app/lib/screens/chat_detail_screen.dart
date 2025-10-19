import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/conversation_controller.dart';
import '../controllers/profile_controller.dart';
import '../controllers/user_controller.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../services/chat_api_client.dart';
import '../widgets/avatar_circle.dart';
import '../widgets/message_bubble.dart';

class ChatDetailScreen extends StatelessWidget {
  const ChatDetailScreen({required this.summary, super.key});

  final ConversationSummary summary;

  @override
  Widget build(BuildContext context) {
    final apiClient = context.read<ChatApiClient>();
    final initialResponderId = context.read<UserController>().respondingUser?.id;

    return ChangeNotifierProvider(
      key: ValueKey(summary.id),
      create: (_) => ConversationController(
        apiClient: apiClient,
        conversationId: summary.id,
        initialDisplayName: summary.displayName,
        initialResponderId: initialResponderId,
      ),
      child: _ConversationWorkspace(summary: summary),
    );
  }
}

class _ConversationWorkspace extends StatefulWidget {
  const _ConversationWorkspace({required this.summary});

  final ConversationSummary summary;

  @override
  State<_ConversationWorkspace> createState() => _ConversationWorkspaceState();
}

class _ConversationWorkspaceState extends State<_ConversationWorkspace> {
  final TextEditingController _composerController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  bool _shouldAutoScroll = true;
  int _lastMessageCount = 0;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_handleScrollPosition);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_handleScrollPosition);
    _composerController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _handleScrollPosition() {
    if (!_scrollController.hasClients) return;
    final maxScroll = _scrollController.position.maxScrollExtent;
    final current = _scrollController.offset;
    const threshold = 96.0;
    _shouldAutoScroll = current >= maxScroll - threshold;
  }

  void _maybeScrollToBottom({bool force = false}) {
    if (!_scrollController.hasClients) return;
    if (!force && !_shouldAutoScroll) return;
    final maxScroll = _scrollController.position.maxScrollExtent;
    if (maxScroll <= 0) return;
    _scrollController.animateTo(
      maxScroll,
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOut,
    );
  }

  List<Widget> _buildMessages(
    List<ChatMessage> messages,
    ConversationController controller,
  ) {
    final widgets = <Widget>[];
    DateTime? lastDay;

    for (var i = 0; i < messages.length; i++) {
      final message = messages[i];
      final isNewDay = lastDay == null || !_isSameDay(lastDay!, message.timestamp);
      if (isNewDay) {
        widgets.add(_DayDivider(date: message.timestamp));
        lastDay = message.timestamp;
      }

      final previous = i > 0 ? messages[i - 1] : null;
      final isGrouped = previous != null &&
          previous.author == message.author &&
          _isSameDay(previous.timestamp, message.timestamp);

      widgets.add(
        MessageBubble(
          message: message,
          isGrouped: isGrouped,
          action: controller.pendingAiMessage != null &&
                  controller.pendingAiMessage!.id == message.id &&
                  message.author == 'ai' &&
                  message.isScheduled
              ? _EditScheduledButton(
                  controller: controller,
                  onRecovered: (draft) {
                    setState(() {
                      _composerController.text = draft;
                      _composerController.selection =
                          TextSelection.collapsed(offset: draft.length);
                      _shouldAutoScroll = true;
                    });
                  },
                )
              : null,
        ),
      );
    }

    return widgets;
  }

  @override
  Widget build(BuildContext context) {
    final respondingUserId = context.select<UserController, String?>(
      (users) => users.respondingUser?.id,
    );

    return Consumer<ConversationController>(
      builder: (context, controller, _) {
        controller.updateResponder(respondingUserId);
        final messages = controller.messages;
        final aiDraft = controller.aiDraft;

        if (_lastMessageCount != messages.length) {
          final shouldForce = _shouldAutoScroll || _lastMessageCount == 0;
          _lastMessageCount = messages.length;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            _maybeScrollToBottom(force: shouldForce);
          });
        }

        return Scaffold(
          backgroundColor: const Color(0xFF0B141A),
          appBar: AppBar(
            backgroundColor: const Color(0xFF111B21),
            foregroundColor: const Color(0xFFE9EDEF),
            automaticallyImplyLeading: Navigator.of(context).canPop(),
            titleSpacing: 0,
            title: _ChatHeader(controller: controller, summary: widget.summary),
          ),
          body: Column(
            children: [
              if (controller.error != null)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                  child: _ErrorBanner(
                    error: controller.error!,
                    onDismissed: controller.clearError,
                  ),
                ),
              Expanded(
                child: Container(
                  decoration: const BoxDecoration(color: Color(0xFF0B141A)),
                  child: controller.isLoading && messages.isEmpty
                      ? const Center(
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation(Color(0xFF00A884)),
                          ),
                        )
                      : RefreshIndicator(
                          backgroundColor: const Color(0xFF111B21),
                          color: const Color(0xFF00A884),
                          onRefresh: controller.refresh,
                          child: ListView(
                            controller: _scrollController,
                            physics: const AlwaysScrollableScrollPhysics(),
                            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
                            children: messages.isEmpty
                                ? const [
                                    SizedBox(height: 160),
                                    _NoMessagesHint(),
                                  ]
                                : _buildMessages(messages, controller),
                          ),
                        ),
                ),
              ),
              if (!controller.aiEnabled)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: FilledButton.icon(
                      onPressed: controller.isDrafting
                          ? null
                          : () async {
                              await controller.fetchDraft();
                              final draft = controller.aiDraft;
                              if (draft != null && mounted) {
                                setState(() {
                                  _composerController.text = draft;
                                  _composerController.selection =
                                      TextSelection.collapsed(offset: draft.length);
                                  _shouldAutoScroll = true;
                                });
                              }
                            },
                      icon: controller.isDrafting
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.auto_fix_high_rounded),
                      label: Text(controller.isDrafting ? 'Drafting…' : 'Generate AI draft'),
                    ),
                  ),
                ),
              if (aiDraft != null && !controller.aiEnabled)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                  child: _AiDraftPreview(
                    draft: aiDraft,
                    onEdit: () {
                      setState(() {
                        _composerController.text = aiDraft;
                        _composerController.selection =
                            TextSelection.collapsed(offset: aiDraft.length);
                        _shouldAutoScroll = true;
                      });
                    },
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                child: _ComposerBar(
                  controller: controller,
                  textController: _composerController,
                  onSend: () => setState(() => _shouldAutoScroll = true),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ChatHeader extends StatelessWidget {
  const _ChatHeader({required this.controller, required this.summary});

  final ConversationController controller;
  final ConversationSummary summary;

  @override
  Widget build(BuildContext context) {
    final name = controller.displayName.isEmpty ? summary.displayName : controller.displayName;
    final subtitle = controller.detail?.phoneNumber ?? controller.conversationId;
    final photoUrl = context.select<ProfileController, String?>(
      (profile) => profile.photoFor(summary.id),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            AvatarCircle(
              label: name,
              size: 44,
              image: photoUrl != null ? NetworkImage(photoUrl) : null,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: const TextStyle(
                      color: Color(0xFFE9EDEF),
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    style: const TextStyle(color: Color(0xFF8696A0), fontSize: 13),
                  ),
                ],
              ),
            ),
            _InboxAiToggle(
              enabled: controller.aiEnabled,
              onToggle: controller.toggleAi,
              busy: controller.isDrafting || controller.isCancellingPendingAi,
            ),
          ],
        ),
        const SizedBox(height: 12),
        const _RespondingUserSelector(),
        const SizedBox(height: 12),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            _PersonaBadge(isEnabled: controller.aiEnabled),
            _AutoReplySwitch(
              value: controller.aiEnabled,
              onChanged: controller.toggleAi,
            ),
          ],
        ),
      ],
    );
  }
}

class _RespondingUserSelector extends StatelessWidget {
  const _RespondingUserSelector();

  @override
  Widget build(BuildContext context) {
    final userController = context.watch<UserController>();
    final users = userController.availableUsers;
    if (users.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'AI replies as',
          style: TextStyle(
            color: Color(0xFF8696A0),
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final user in users)
              Builder(
                builder: (context) {
                  final isSelected = userController.isRespondingUser(user);
                  final labelText = userController.isCurrentUser(user)
                      ? '${user.displayName} (You)'
                      : user.displayName;
                  return ChoiceChip(
                    selected: isSelected,
                    onSelected: (_) => userController.switchRespondingUser(user.id),
                    backgroundColor: const Color(0x33202C33),
                    selectedColor: const Color(0xFF00A884),
                    labelPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    label: Text(
                      labelText,
                      style: TextStyle(
                        color: isSelected ? Colors.white : const Color(0xFFE9EDEF),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  );
                },
              ),
          ],
        ),
      ],
    );
  }
}

class _InboxAiToggle extends StatelessWidget {
  const _InboxAiToggle({required this.enabled, required this.onToggle, this.busy = false});

  final bool enabled;
  final ValueChanged<bool> onToggle;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton(
      onPressed: busy ? null : () => onToggle(!enabled),
      style: OutlinedButton.styleFrom(
        backgroundColor: enabled ? const Color(0x3300A884) : const Color(0x33202C33),
        foregroundColor: const Color(0xFFE9EDEF),
        side: BorderSide(color: enabled ? const Color(0xFF00A884) : const Color(0xFF243038)),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(enabled ? Icons.bolt : Icons.bolt_outlined, size: 18, color: const Color(0xFF00A884)),
          const SizedBox(width: 8),
          Text(
            'Inbox AI: ${enabled ? 'On' : 'Off'}',
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _PersonaBadge extends StatelessWidget {
  const _PersonaBadge({required this.isEnabled});

  final bool isEnabled;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0x33202C33),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFF243038)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: const LinearGradient(
                  colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                border: Border.all(color: const Color(0x338696A0)),
              ),
              child: const Icon(Icons.bolt, color: Colors.white, size: 16),
            ),
            const SizedBox(width: 8),
            Text(
              isEnabled ? 'Default AI persona' : 'Manual replies',
              style: const TextStyle(color: Color(0xFFE9EDEF), fontSize: 13, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}

class _AutoReplySwitch extends StatelessWidget {
  const _AutoReplySwitch({required this.value, required this.onChanged});

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0x33202C33),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0x33243038)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 260),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Switch(
              value: value,
              onChanged: (next) => onChanged(next),
              activeColor: const Color(0xFF00A884),
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                'Auto replies for this chat',
                style: const TextStyle(
                  color: Color(0xFFE9EDEF),
                  fontWeight: FontWeight.w600,
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.error, required this.onDismissed});

  final Object error;
  final VoidCallback onDismissed;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0x33F15C6D),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0x66F15C6D)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.error_outline, color: Color(0xFFF15C6D)),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                '$error',
                style: const TextStyle(color: Color(0xFFF15C6D), height: 1.4),
              ),
            ),
            IconButton(
              onPressed: onDismissed,
              icon: const Icon(Icons.close, color: Color(0xFFF15C6D)),
            ),
          ],
        ),
      ),
    );
  }
}

class _ComposerBar extends StatefulWidget {
  const _ComposerBar({
    required this.controller,
    required this.textController,
    required this.onSend,
  });

  final ConversationController controller;
  final TextEditingController textController;
  final VoidCallback onSend;

  @override
  State<_ComposerBar> createState() => _ComposerBarState();
}

class _ComposerBarState extends State<_ComposerBar> {
  @override
  Widget build(BuildContext context) {
    final isSending = widget.controller.isSending;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFF202C33),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0x1A8696A0)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: widget.textController,
                maxLines: 6,
                minLines: 1,
                style: const TextStyle(color: Color(0xFFE9EDEF), height: 1.4),
                decoration: const InputDecoration(
                  hintText: 'Type a message',
                  hintStyle: TextStyle(color: Color(0xFF8696A0)),
                  border: InputBorder.none,
                  isCollapsed: true,
                ),
                cursorColor: const Color(0xFF00A884),
                textInputAction: TextInputAction.newline,
              ),
            ),
            const SizedBox(width: 16),
            FilledButton(
              onPressed: isSending
                  ? null
                  : () async {
                      final text = widget.textController.text.trim();
                      if (text.isEmpty) return;
                      widget.onSend();
                      final senderId = context.read<UserController>().currentUser?.id;
                      await widget.controller.sendMessage(text, senderId: senderId);
                      if (mounted) {
                        widget.textController.clear();
                      }
                    },
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF00A884),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              ),
              child: isSending
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.send_rounded),
            ),
          ],
        ),
      ),
    );
  }
}

class _AiDraftPreview extends StatelessWidget {
  const _AiDraftPreview({required this.draft, required this.onEdit});

  final String draft;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFF182229),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0x1A8696A0)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.bolt, color: Color(0xFF00A884)),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                draft,
                style: const TextStyle(color: Color(0xFFE9EDEF), height: 1.5),
              ),
            ),
            IconButton(
              onPressed: onEdit,
              icon: const Icon(Icons.edit, color: Color(0xFF00A884)),
            ),
          ],
        ),
      ),
    );
  }
}

class _EditScheduledButton extends StatelessWidget {
  const _EditScheduledButton({required this.controller, required this.onRecovered});

  final ConversationController controller;
  final ValueChanged<String> onRecovered;

  @override
  Widget build(BuildContext context) {
    final isBusy = controller.isCancellingPendingAi;

    return OutlinedButton.icon(
      onPressed: isBusy
          ? null
          : () async {
              final draft = await controller.cancelPendingAiMessage();
              if (draft != null) {
                onRecovered(draft);
              }
            },
      style: OutlinedButton.styleFrom(
        foregroundColor: const Color(0xFF00A884),
        side: const BorderSide(color: Color(0xFF00A884)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
      icon: isBusy
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF00A884)),
            )
          : const Icon(Icons.edit_outlined, size: 18),
      label: const Text('Edit before sending'),
    );
  }
}

class _DayDivider extends StatelessWidget {
  const _DayDivider({required this.date});

  final DateTime date;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        children: [
          const Expanded(
            child: Divider(color: Color(0x338696A0), thickness: 1, endIndent: 12),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF182229),
              borderRadius: BorderRadius.circular(24),
            ),
            child: Text(
              _formatDate(date),
              style: const TextStyle(
                color: Color(0xFF00A884),
                fontWeight: FontWeight.w600,
                fontSize: 12,
              ),
            ),
          ),
          const Expanded(
            child: Divider(color: Color(0x338696A0), thickness: 1, indent: 12),
          ),
        ],
      ),
    );
  }
}

class _NoMessagesHint extends StatelessWidget {
  const _NoMessagesHint();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: const [
        Icon(Icons.chat_bubble_outline, size: 48, color: Color(0xFF8696A0)),
        SizedBox(height: 12),
        Text(
          'No messages yet',
          style: TextStyle(color: Color(0xFFE9EDEF), fontWeight: FontWeight.w600),
        ),
        SizedBox(height: 6),
        Text(
          'Send a WhatsApp message to see it appear instantly.',
          style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

bool _isSameDay(DateTime a, DateTime b) {
  return a.year == b.year && a.month == b.month && a.day == b.day;
}

String _formatDate(DateTime date) {
  final now = DateTime.now();
  if (_isSameDay(now, date)) return 'Today';
  final yesterday = DateTime(now.year, now.month, now.day - 1);
  if (_isSameDay(yesterday, date)) return 'Yesterday';
  return '${date.month}/${date.day}/${date.year}';
}
