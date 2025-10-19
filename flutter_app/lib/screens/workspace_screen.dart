import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/conversation_controller.dart';
import '../controllers/inbox_controller.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../services/chat_api_client.dart';
import '../widgets/conversation_tile.dart';
import '../widgets/message_bubble.dart';

class WorkspaceScreen extends StatefulWidget {
  const WorkspaceScreen({super.key});

  @override
  State<WorkspaceScreen> createState() => _WorkspaceScreenState();
}

class _WorkspaceScreenState extends State<WorkspaceScreen> {
  String? _activeConversationId;

  @override
  Widget build(BuildContext context) {
    final background = const Color(0xFF0B141A);

    return Scaffold(
      backgroundColor: background,
      body: SafeArea(
        child: Container(
          color: background,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final isCompact = constraints.maxWidth < 760;
              return Consumer<InboxController>(
                builder: (context, inbox, _) {
                  final conversations = inbox.conversations;
                  ConversationSummary? activeSummary;

                  if (conversations.isNotEmpty) {
                    activeSummary = conversations.firstWhere(
                      (summary) => summary.id == _activeConversationId,
                      orElse: () => conversations.first,
                    );

                    if (_activeConversationId != activeSummary.id) {
                      WidgetsBinding.instance.addPostFrameCallback((_) {
                        if (!mounted) return;
                        setState(() => _activeConversationId = activeSummary!.id);
                      });
                    }
                  } else if (_activeConversationId != null) {
                    WidgetsBinding.instance.addPostFrameCallback((_) {
                      if (!mounted) return;
                      setState(() => _activeConversationId = null);
                    });
                  }

                  final sidebar = _Sidebar(
                    controller: inbox,
                    activeConversationId: _activeConversationId,
                    onSelect: (summary) {
                      if (_activeConversationId == summary.id) return;
                      setState(() => _activeConversationId = summary.id);
                    },
                  );

                  final apiClient = context.read<ChatApiClient>();

                  final conversationPane = activeSummary == null
                      ? const _EmptyConversationPane()
                      : ChangeNotifierProvider(
                          key: ValueKey(activeSummary.id),
                          create: (_) => ConversationController(
                            apiClient: apiClient,
                            conversationId: activeSummary.id,
                            initialDisplayName: activeSummary.displayName,
                          ),
                          child: _ConversationWorkspace(
                            placeholderName: activeSummary.displayName,
                          ),
                        );

                  if (isCompact) {
                    return Column(
                      children: [
                        SizedBox(height: 320, child: sidebar),
                        const Divider(height: 1, color: Color(0x22E9EDEF)),
                        Expanded(child: conversationPane),
                      ],
                    );
                  }

                  return Row(
                    children: [
                      SizedBox(width: 320, child: sidebar),
                      const VerticalDivider(width: 1, color: Color(0x22E9EDEF)),
                      Expanded(child: conversationPane),
                    ],
                  );
                },
              );
            },
          ),
        ),
      ),
    );
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({
    required this.controller,
    required this.activeConversationId,
    required this.onSelect,
  });

  final InboxController controller;
  final String? activeConversationId;
  final ValueChanged<ConversationSummary> onSelect;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [Color(0xFF111B21), Color(0xFF0B141A)],
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Pow Team Chat',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: Color(0xFFE9EDEF),
              ),
            ),
            const SizedBox(height: 6),
            const Text(
              'Switch between teammates to steer the conversation.',
              style: TextStyle(
                color: Color(0xFF8696A0),
                fontSize: 14,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 24),
            Expanded(
              child: controller.isLoading && controller.conversations.isEmpty
                  ? const Center(
                      child: CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation(Color(0xFF00A884)),
                      ),
                    )
                  : controller.error != null && controller.conversations.isEmpty
                      ? _SidebarError(error: controller.error!, onRetry: controller.refresh)
                      : RefreshIndicator(
                          backgroundColor: const Color(0xFF111B21),
                          color: const Color(0xFF00A884),
                          onRefresh: controller.refresh,
                          child: controller.conversations.isEmpty
                              ? ListView(
                                  physics: const AlwaysScrollableScrollPhysics(),
                                  children: const [
                                    SizedBox(height: 160),
                                    _SidebarEmptyState(),
                                  ],
                                )
                              : ListView.separated(
                                  physics: const AlwaysScrollableScrollPhysics(),
                                  itemCount: controller.conversations.length,
                                  separatorBuilder: (_, __) => const SizedBox(height: 12),
                                  itemBuilder: (context, index) {
                                    final summary = controller.conversations[index];
                                    return ConversationTile(
                                      summary: summary,
                                      isSelected: summary.id == activeConversationId,
                                      onTap: () => onSelect(summary),
                                    );
                                  },
                                ),
                        ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SidebarError extends StatelessWidget {
  const _SidebarError({required this.error, required this.onRetry});

  final Object error;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.wifi_off, size: 40, color: Color(0xFF8696A0)),
        const SizedBox(height: 12),
        const Text(
          'Unable to load inbox',
          style: TextStyle(
            color: Color(0xFFE9EDEF),
            fontWeight: FontWeight.w600,
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
    );
  }
}

class _SidebarEmptyState extends StatelessWidget {
  const _SidebarEmptyState();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: const [
        Icon(Icons.chat_bubble_outline, size: 60, color: Color(0xFF8696A0)),
        SizedBox(height: 16),
        Text(
          'No conversations yet',
          style: TextStyle(
            color: Color(0xFFE9EDEF),
            fontWeight: FontWeight.w600,
          ),
        ),
        SizedBox(height: 8),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: 8),
          child: Text(
            'Messages from your Twilio sandbox will show up here instantly.',
            style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
            textAlign: TextAlign.center,
          ),
        ),
      ],
    );
  }
}

class _EmptyConversationPane extends StatelessWidget {
  const _EmptyConversationPane();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: Color(0xFF111B21),
      ),
      child: const Center(
        child: Text(
          'Select a teammate to view the conversation',
          style: TextStyle(color: Color(0xFF8696A0), fontSize: 16),
        ),
      ),
    );
  }
}

class _ConversationWorkspace extends StatefulWidget {
  const _ConversationWorkspace({required this.placeholderName});

  final String placeholderName;

  @override
  State<_ConversationWorkspace> createState() => _ConversationWorkspaceState();
}

class _ConversationWorkspaceState extends State<_ConversationWorkspace> {
  final TextEditingController _composerController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _composerController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    if (!_scrollController.hasClients) return;
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 300),
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
    return Consumer<ConversationController>(
      builder: (context, controller, _) {
        final messages = controller.messages;
        final aiDraft = controller.aiDraft;

        WidgetsBinding.instance.addPostFrameCallback((_) => _scrollToBottom());

        return Container(
          decoration: const BoxDecoration(color: Color(0xFF111B21)),
          child: Column(
            children: [
              _WorkspaceHeader(controller: controller, placeholderName: widget.placeholderName),
              if (controller.error != null)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
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
                            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
                            physics: const AlwaysScrollableScrollPhysics(),
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
                  padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
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
                  padding: const EdgeInsets.fromLTRB(24, 12, 24, 0),
                  child: _AiDraftPreview(
                    draft: aiDraft,
                    onEdit: () {
                      setState(() {
                        _composerController.text = aiDraft;
                        _composerController.selection =
                            TextSelection.collapsed(offset: aiDraft.length);
                      });
                    },
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
                child: _ComposerBar(
                  controller: controller,
                  textController: _composerController,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _WorkspaceHeader extends StatelessWidget {
  const _WorkspaceHeader({required this.controller, required this.placeholderName});

  final ConversationController controller;
  final String placeholderName;

  @override
  Widget build(BuildContext context) {
    final name = controller.displayName.isEmpty ? placeholderName : controller.displayName;
    final subtitle = controller.detail?.phoneNumber ?? controller.conversationId;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
      decoration: const BoxDecoration(
        color: Color(0xFF111B21),
        border: Border(bottom: BorderSide(color: Color(0x1A8696A0))),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      style: const TextStyle(
                        color: Color(0xFFE9EDEF),
                        fontSize: 20,
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
          const SizedBox(height: 16),
          Row(
            children: [
              _PersonaBadge(isEnabled: controller.aiEnabled),
              const SizedBox(width: 12),
              _AutoReplySwitch(
                value: controller.aiEnabled,
                onChanged: controller.toggleAi,
              ),
            ],
          ),
        ],
      ),
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
    return Row(
      children: [
        Switch(
          value: value,
          onChanged: (next) => onChanged(next),
          activeColor: const Color(0xFF00A884),
        ),
        const SizedBox(width: 6),
        const Text(
          'Auto replies for this chat',
          style: TextStyle(color: Color(0xFFE9EDEF), fontWeight: FontWeight.w600),
        ),
      ],
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
  const _ComposerBar({required this.controller, required this.textController});

  final ConversationController controller;
  final TextEditingController textController;

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
                  hintText: 'Share an update as the selected teammate',
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
                      final text = widget.textController.text;
                      await widget.controller.sendMessage(text);
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
