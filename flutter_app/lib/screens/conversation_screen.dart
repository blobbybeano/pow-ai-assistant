import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../controllers/conversation_controller.dart';
import '../models/message.dart';
import '../widgets/message_bubble.dart';

class ConversationScreenArgs {
  const ConversationScreenArgs({
    required this.conversationId,
    required this.displayName,
  });

  final String conversationId;
  final String displayName;
}

class ConversationScreen extends StatefulWidget {
  const ConversationScreen({super.key, required this.args});

  static const routeName = '/conversation';

  final ConversationScreenArgs args;

  @override
  State<ConversationScreen> createState() => _ConversationScreenState();
}

class _ConversationScreenState extends State<ConversationScreen> {
  final TextEditingController _composerController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _composerController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationController>(
      builder: (context, controller, _) {
        final messages = controller.messages;

        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollController.hasClients) {
            _scrollController.animateTo(
              _scrollController.position.maxScrollExtent,
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOut,
            );
          }
        });

        return Scaffold(
          appBar: AppBar(
            title: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(controller.displayName),
                Text(
                  widget.args.conversationId,
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: Colors.black54),
                ),
              ],
            ),
            actions: [
              Row(
                children: [
                  const Text('Pow AI Autoreply'),
                  Switch(
                    value: controller.aiEnabled,
                    onChanged: (value) => controller.toggleAi(value),
                  ),
                ],
              ),
              const SizedBox(width: 12),
            ],
          ),
          body: Column(
            children: [
              if (controller.error != null)
                Container(
                  width: double.infinity,
                  margin: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.redAccent.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.error_outline, color: Colors.redAccent),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          '${controller.error}',
                          style: Theme.of(context)
                              .textTheme
                              .bodyMedium
                              ?.copyWith(color: Colors.redAccent),
                        ),
                      ),
                      IconButton(
                        onPressed: () => controller.clearError(),
                        icon: const Icon(Icons.close, color: Colors.redAccent),
                        tooltip: 'Dismiss',
                      ),
                    ],
                  ),
                ),
              Expanded(
                child: Container(
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.only(
                      topLeft: Radius.circular(24),
                      topRight: Radius.circular(24),
                    ),
                  ),
                  child: controller.isLoading && messages.isEmpty
                      ? const Center(child: CircularProgressIndicator())
                      : RefreshIndicator(
                          onRefresh: controller.refresh,
                          child: ListView(
                            controller: _scrollController,
                            physics: const AlwaysScrollableScrollPhysics(),
                            padding: const EdgeInsets.symmetric(vertical: 16),
                            children: messages.isEmpty
                                ? const [
                                    SizedBox(height: 160),
                                    _NoMessagesHint(),
                                  ]
                                : _buildMessageWidgets(messages),
                          ),
                        ),
                ),
              ),
              if (!controller.aiEnabled)
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                  child: Row(
                    children: [
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: controller.isDrafting
                              ? null
                              : () async {
                                  await controller.fetchDraft();
                                  if (controller.aiDraft != null && mounted) {
                                    _composerController.text = controller.aiDraft!;
                                  }
                                },
                          icon: controller.isDrafting
                              ? const SizedBox(
                                  height: 16,
                                  width: 16,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.auto_fix_high),
                          label: Text(controller.isDrafting ? 'Drafting…' : 'AI Draft'),
                        ),
                      ),
                    ],
                  ),
                ),
              if (controller.aiDraft != null && !controller.aiEnabled)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: const Color(0xFF246BFD).withOpacity(0.08),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.bolt, color: Color(0xFF246BFD)),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              controller.aiDraft!,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium
                                  ?.copyWith(color: Colors.black87),
                            ),
                          ),
                          IconButton(
                            onPressed: () {
                              setState(() {
                                _composerController.text = controller.aiDraft!;
                              });
                            },
                            icon: const Icon(Icons.edit),
                            tooltip: 'Edit draft',
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              _ComposerBar(
                controller: controller,
                composerController: _composerController,
              ),
            ],
          ),
        );
      },
    );
  }
}

List<Widget> _buildMessageWidgets(List<ChatMessage> messages) {
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
    widgets.add(MessageBubble(message: message, isGrouped: isGrouped));
  }
  return widgets;
}

bool _isSameDay(DateTime a, DateTime b) {
  return a.year == b.year && a.month == b.month && a.day == b.day;
}

class _DayDivider extends StatelessWidget {
  const _DayDivider({required this.date});

  final DateTime date;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        children: [
          const Expanded(
            child: Divider(
              color: Colors.black12,
              thickness: 1,
              endIndent: 12,
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF246BFD).withOpacity(0.12),
              borderRadius: BorderRadius.circular(24),
            ),
            child: Text(
              _formatDate(date),
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: const Color(0xFF246BFD), fontWeight: FontWeight.w600),
            ),
          ),
          const Expanded(
            child: Divider(
              color: Colors.black12,
              thickness: 1,
              indent: 12,
            ),
          ),
        ],
      ),
    );
  }
}

String _formatDate(DateTime date) {
  final now = DateTime.now();
  if (_isSameDay(now, date)) return 'Today';
  final yesterday = DateTime(now.year, now.month, now.day - 1);
  if (_isSameDay(yesterday, date)) return 'Yesterday';
  return DateFormat.MMMd().format(date);
}

class _NoMessagesHint extends StatelessWidget {
  const _NoMessagesHint();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        children: [
          Icon(Icons.chat_bubble_outline,
              size: 48, color: Colors.black.withOpacity(0.18)),
          const SizedBox(height: 12),
          Text(
            'No messages yet',
            style: Theme.of(context).textTheme.titleMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 6),
          Text(
            'Send a WhatsApp message to this conversation to see it appear instantly.',
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: Colors.black54),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

class _ComposerBar extends StatefulWidget {
  const _ComposerBar({
    required this.controller,
    required this.composerController,
  });

  final ConversationController controller;
  final TextEditingController composerController;

  @override
  State<_ComposerBar> createState() => _ComposerBarState();
}

class _ComposerBarState extends State<_ComposerBar> {
  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Row(
          children: [
            Expanded(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(24),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.06),
                      offset: const Offset(0, 6),
                      blurRadius: 12,
                    ),
                  ],
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: TextField(
                    controller: widget.composerController,
                    maxLines: 4,
                    minLines: 1,
                    textInputAction: TextInputAction.newline,
                    decoration: const InputDecoration(
                      border: InputBorder.none,
                      hintText: 'Type a reply…',
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            FilledButton(
              onPressed: widget.controller.isSending
                  ? null
                  : () async {
                      final text = widget.composerController.text;
                      await widget.controller.sendMessage(text);
                      if (mounted) {
                        widget.composerController.clear();
                      }
                    },
              child: widget.controller.isSending
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
