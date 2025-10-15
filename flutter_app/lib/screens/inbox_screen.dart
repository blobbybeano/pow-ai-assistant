import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/inbox_controller.dart';
import '../models/conversation.dart';
import '../widgets/conversation_tile.dart';
import 'conversation_screen.dart';

class InboxScreen extends StatelessWidget {
  const InboxScreen({super.key});

  static const routeName = '/';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('PowWash WhatsApp Inbox'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => context.read<InboxController>().refresh(),
          ),
        ],
      ),
      body: SafeArea(
        child: Consumer<InboxController>(
          builder: (context, controller, _) {
            if (controller.isLoading && controller.conversations.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            if (controller.error != null && controller.conversations.isEmpty) {
              return _ErrorState(error: controller.error!);
            }

            if (controller.conversations.isEmpty) {
              return RefreshIndicator(
                onRefresh: controller.refresh,
                child: ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  children: const [
                    SizedBox(height: 120),
                    _EmptyState(),
                  ],
                ),
              );
            }

            return RefreshIndicator(
              onRefresh: controller.refresh,
              child: ListView.separated(
                physics: const AlwaysScrollableScrollPhysics(),
                itemCount: controller.conversations.length,
                separatorBuilder: (_, __) => const Divider(height: 1, indent: 80),
                itemBuilder: (context, index) {
                  final summary = controller.conversations[index];
                  return ConversationTile(
                    summary: summary,
                    onTap: () => _openConversation(context, summary),
                  );
                },
              ),
            );
          },
        ),
      ),
    );
  }

  void _openConversation(BuildContext context, ConversationSummary summary) {
    Navigator.of(context).pushNamed(
      ConversationScreen.routeName,
      arguments: ConversationScreenArgs(
        conversationId: summary.id,
        displayName: summary.displayName,
      ),
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.error});

  final Object error;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.wifi_off, size: 48, color: Colors.redAccent),
          const SizedBox(height: 12),
          Text(
            'Unable to load inbox',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text(
            '$error',
            textAlign: TextAlign.center,
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: Colors.black54),
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: () => context.read<InboxController>().refresh(),
            icon: const Icon(Icons.refresh),
            label: const Text('Retry'),
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
    return Column(
      children: [
        const Icon(Icons.chat_bubble_outline, size: 72, color: Colors.black26),
        const SizedBox(height: 16),
        Text(
          'No conversations yet',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Text(
            'Messages from your Twilio sandbox will show up here instantly. Send a test message to your sandbox number to get started.',
            textAlign: TextAlign.center,
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(color: Colors.black54),
          ),
        ),
      ],
    );
  }
}
