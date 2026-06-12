import 'package:flutter/material.dart';

import '../models/conversation.dart';

class AiTrainingDashboardScreen extends StatefulWidget {
  const AiTrainingDashboardScreen({super.key, required this.conversations});

  final List<ConversationSummary> conversations;

  @override
  State<AiTrainingDashboardScreen> createState() => _AiTrainingDashboardScreenState();
}

class _AiTrainingDashboardScreenState extends State<AiTrainingDashboardScreen> {
  final Set<String> _selectedConversationIds = <String>{};
  final TextEditingController _pricingNotesController = TextEditingController();
  final TextEditingController _trainingNotesController = TextEditingController();

  @override
  void dispose() {
    _pricingNotesController.dispose();
    _trainingNotesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final conversations = widget.conversations;
    final selectedCount = _selectedConversationIds.length;

    return Scaffold(
      backgroundColor: const Color(0xFF0B141A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF111B21),
        foregroundColor: const Color(0xFFE9EDEF),
        title: const Text('AI Training Dashboard'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          Container(
            decoration: BoxDecoration(
              color: const Color(0xFF111B21),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0x33243038)),
            ),
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Training summary',
                  style: TextStyle(
                    color: Color(0xFFE9EDEF),
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  'Select which customer conversations should be included in the next AI training batch.'
                  ' Highlight pricing notes or service changes so the assistant can quote accurately.',
                  style: const TextStyle(
                    color: Color(0xFF8696A0),
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    _SummaryPill(
                      label: 'Total conversations',
                      value: conversations.length.toString(),
                    ),
                    _SummaryPill(
                      label: 'Selected for training',
                      value: selectedCount.toString(),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: selectedCount == 0
                      ? null
                      : () {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              backgroundColor: const Color(0xFF0B5D47),
                              content: Text(
                                'Prepared training package for $selectedCount conversation(s).',
                              ),
                            ),
                          );
                        },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF00A884),
                    foregroundColor: Colors.white,
                  ),
                  icon: const Icon(Icons.dataset_rounded),
                  label: const Text('Generate training package'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const _SectionHeader(title: 'Conversation library'),
          const SizedBox(height: 12),
          if (conversations.isEmpty)
            Container(
              decoration: BoxDecoration(
                color: const Color(0xFF111B21),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0x33243038)),
              ),
              padding: const EdgeInsets.all(20),
              child: const Text(
                'No conversations found yet. New enquiries will appear here so you can curate training data.',
                style: TextStyle(color: Color(0xFF8696A0), height: 1.4),
              ),
            )
          else
            Column(
              children: [
                for (final conversation in conversations)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _TrainingConversationTile(
                      conversation: conversation,
                      isSelected: _selectedConversationIds.contains(conversation.id),
                      onToggle: () => _toggleSelection(conversation.id),
                    ),
                  ),
              ],
            ),
          const SizedBox(height: 24),
          const _SectionHeader(title: 'Pricing insights'),
          const SizedBox(height: 12),
          Container(
            decoration: BoxDecoration(
              color: const Color(0xFF111B21),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0x33243038)),
            ),
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Update pricing cues',
                  style: TextStyle(
                    color: Color(0xFFE9EDEF),
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _pricingNotesController,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    hintText:
                        'Document promotions, travel fees, seasonal pricing, or packages the AI should reference.',
                  ),
                ),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: () {
                      FocusScope.of(context).unfocus();
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          backgroundColor: Color(0xFF0B5D47),
                          content: Text('Pricing notes saved for the workspace.'),
                        ),
                      );
                    },
                    icon: const Icon(Icons.save_rounded),
                    label: const Text('Save notes'),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          const _SectionHeader(title: 'Additional training assets'),
          const SizedBox(height: 12),
          Container(
            decoration: BoxDecoration(
              color: const Color(0xFF111B21),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0x33243038)),
            ),
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Upload resources and scenarios',
                  style: TextStyle(
                    color: Color(0xFFE9EDEF),
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: const [
                    _ResourceChip(label: 'Service catalog'),
                    _ResourceChip(label: 'FAQ updates'),
                    _ResourceChip(label: 'Knowledge base links'),
                  ],
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _trainingNotesController,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    hintText: 'Capture edge cases, tone preferences, or escalation rules for the AI.',
                  ),
                ),
                const SizedBox(height: 12),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: () {
                      FocusScope.of(context).unfocus();
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          backgroundColor: Color(0xFF0B5D47),
                          content: Text('Training notes synced.'),
                        ),
                      );
                    },
                    icon: const Icon(Icons.check_circle_outline),
                    label: const Text('Mark as ready'),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _toggleSelection(String id) {
    setState(() {
      if (_selectedConversationIds.contains(id)) {
        _selectedConversationIds.remove(id);
      } else {
        _selectedConversationIds.add(id);
      }
    });
  }
}

class _TrainingConversationTile extends StatelessWidget {
  const _TrainingConversationTile({
    required this.conversation,
    required this.isSelected,
    required this.onToggle,
  });

  final ConversationSummary conversation;
  final bool isSelected;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final preview = conversation.lastMessage?.text?.trim();
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF111B21),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isSelected ? const Color(0xFF00A884) : const Color(0x33243038),
          width: 1.5,
        ),
      ),
      padding: const EdgeInsets.all(16),
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
                      conversation.displayName,
                      style: const TextStyle(
                        color: Color(0xFFE9EDEF),
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      conversation.phoneNumber,
                      style: const TextStyle(color: Color(0xFF8696A0), fontSize: 12),
                    ),
                  ],
                ),
              ),
              Switch.adaptive(
                value: isSelected,
                onChanged: (_) => onToggle(),
                activeColor: const Color(0xFF00A884),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            (preview != null && preview.isNotEmpty)
                ? preview
                : 'No recent messages yet. Pull in history to give the AI context.',
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Color(0xFFB6C1C9),
              height: 1.4,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _TagChip(label: conversation.aiEnabled ? 'AI enabled' : 'AI paused'),
              if (conversation.unreadCount > 0)
                _TagChip(label: '${conversation.unreadCount} unread'),
              _TagChip(label: 'ID ${conversation.id.substring(0, 6)}'),
            ],
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: const TextStyle(
        color: Color(0xFFE9EDEF),
        fontSize: 17,
        fontWeight: FontWeight.w700,
      ),
    );
  }
}

class _SummaryPill extends StatelessWidget {
  const _SummaryPill({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF0D1D23),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0x332FC6B2)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            value,
            style: const TextStyle(
              color: Color(0xFFE9EDEF),
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: const TextStyle(color: Color(0xFF8696A0), fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _TagChip extends StatelessWidget {
  const _TagChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: const Color(0xFF1F2C34),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0x33243038)),
      ),
      child: Text(
        label,
        style: const TextStyle(color: Color(0xFFB6C1C9), fontSize: 12),
      ),
    );
  }
}

class _ResourceChip extends StatelessWidget {
  const _ResourceChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF1F2C34),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0x332FC6B2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.attach_file, color: Color(0xFF00A884), size: 16),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(color: Color(0xFFE9EDEF), fontSize: 12),
          ),
        ],
      ),
    );
  }
}
