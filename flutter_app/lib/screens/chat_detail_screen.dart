import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/conversation_controller.dart';
import '../controllers/inbox_controller.dart';
import '../controllers/profile_controller.dart';
import '../controllers/user_controller.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../services/chat_api_client.dart';
import '../widgets/avatar_circle.dart';
import '../widgets/message_bubble.dart';
import '../widgets/profile_settings_sheet.dart';
import 'ai_training_dashboard_screen.dart';
import 'integration_settings_screen.dart';

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
              ? _PendingAiActionRow(
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
            automaticallyImplyLeading: false,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_rounded),
              tooltip: 'Back',
              onPressed: () => Navigator.of(context).maybePop(),
            ),
            titleSpacing: 0,
            title: _ChatTitle(controller: controller, summary: widget.summary),
            actions: [
              IconButton(
                icon: const Icon(Icons.settings),
                tooltip: 'Settings',
                onPressed: () async {
                  final conversations =
                      context.read<InboxController>().conversations;
                  final action = await showProfileSettingsSheet(
                    context,
                    conversations,
                  );
                  if (!mounted) return;
                  switch (action) {
                    case ProfileSettingsAction.aiTrainingDashboard:
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => AiTrainingDashboardScreen(
                            conversations: conversations,
                          ),
                        ),
                      );
                      break;
                    case ProfileSettingsAction.integrationTokens:
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
              ),
              _AiToggleAction(controller: controller),
            ],
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

class _ChatTitle extends StatelessWidget {
  const _ChatTitle({required this.controller, required this.summary});

  final ConversationController controller;
  final ConversationSummary summary;

  @override
  Widget build(BuildContext context) {
    final name = controller.displayName.isEmpty ? summary.displayName : controller.displayName;
    final subtitle = controller.detail?.phoneNumber ?? controller.conversationId;
    final fallbackPhoto = controller.detail?.profilePhotoUrl ?? summary.profilePhotoUrl;
    final photoUrl = context.select<ProfileController, String?>(
      (profile) => profile.photoFor(summary.id),
    );

    if (fallbackPhoto != null && (photoUrl == null || photoUrl.isEmpty)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!context.mounted) return;
        context.read<ProfileController>().setPhoto(summary.id, fallbackPhoto);
      });
    }

    final resolvedPhoto = photoUrl ?? fallbackPhoto;

    return Row(
      children: [
        AvatarCircle(
          label: name,
          size: 44,
          image: resolvedPhoto != null ? NetworkImage(resolvedPhoto) : null,
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                name,
                style: const TextStyle(
                  color: Color(0xFFE9EDEF),
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
              Text(
                subtitle,
                style: const TextStyle(color: Color(0xFF8696A0), fontSize: 13),
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _AiToggleAction extends StatelessWidget {
  const _AiToggleAction({required this.controller});

  final ConversationController controller;

  @override
  Widget build(BuildContext context) {
    final isBusy = controller.isDrafting || controller.isCancellingPendingAi;
    final label = controller.aiEnabled ? 'AI on' : 'AI off';
    return Padding(
      padding: const EdgeInsets.only(right: 8),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: Color(0xFFE9EDEF),
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(width: 8),
          Switch.adaptive(
            value: controller.aiEnabled,
            onChanged: isBusy ? null : controller.toggleAi,
            activeColor: const Color(0xFF00A884),
          ),
          if (isBusy) ...[
            const SizedBox(width: 4),
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF00A884)),
            ),
          ],
        ],
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
  final List<_PendingAttachment> _pendingAttachments = <_PendingAttachment>[];
  bool _isUploading = false;

  List<Map<String, dynamic>> get _attachmentPayload =>
      _pendingAttachments.map((attachment) => attachment.toJson()).toList();

  Future<void> _pickImages() async {
    if (_isUploading) return;
    final result = await FilePicker.platform.pickFiles(
      allowMultiple: true,
      type: FileType.image,
      withData: true,
    );

    if (result == null || result.files.isEmpty) {
      return;
    }

    setState(() => _isUploading = true);
    final apiClient = context.read<ChatApiClient>();
    final newAttachments = <_PendingAttachment>[];

    for (final file in result.files) {
      final bytes = file.bytes;
      if (bytes == null) {
        continue;
      }

      final name = file.name.isNotEmpty ? file.name : 'photo.jpg';
      final mimeType = _guessMimeType(name);

      try {
        final metadata = await apiClient.uploadImage(
          filename: name,
          mimeType: mimeType,
          bytes: bytes,
        );

        final remoteUrl = metadata['url'] as String?;
        if (remoteUrl == null || remoteUrl.isEmpty) {
          throw Exception('Upload response missing URL');
        }

        newAttachments.add(
          _PendingAttachment(
            id: metadata['id'] as String? ?? remoteUrl,
            filename: metadata['filename'] as String? ?? name,
            mimeType: metadata['contentType'] as String? ?? mimeType,
            url: remoteUrl,
            bytes: bytes,
          ),
        );
      } catch (error) {
        if (!mounted) continue;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Image upload failed: $error')),
        );
      }
    }

    if (newAttachments.isNotEmpty && mounted) {
      setState(() {
        _pendingAttachments.addAll(newAttachments);
      });
    }

    if (mounted) {
      setState(() => _isUploading = false);
    }
  }

  void _removeAttachment(String id) {
    setState(() {
      _pendingAttachments.removeWhere((attachment) => attachment.id == id);
    });
  }

  String _guessMimeType(String filename) {
    final extension = filename.split('.').last.toLowerCase();
    switch (extension) {
      case 'png':
        return 'image/png';
      case 'gif':
        return 'image/gif';
      case 'webp':
        return 'image/webp';
      case 'heic':
        return 'image/heic';
      case 'heif':
        return 'image/heif';
      case 'bmp':
        return 'image/bmp';
      case 'jpeg':
      case 'jpg':
      default:
        return 'image/jpeg';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isSending = widget.controller.isSending;
    final isBusy = isSending || _isUploading || widget.controller.isSendingPendingAi;

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
            IconButton(
              onPressed: isSending || _isUploading ? null : _pickImages,
              icon: _isUploading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF00A884)),
                    )
                  : const Icon(Icons.photo_camera_outlined, color: Color(0xFFE9EDEF)),
              tooltip: 'Attach photo',
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_pendingAttachments.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _AttachmentPreviewList(
                        attachments: _pendingAttachments,
                        onRemove: _removeAttachment,
                      ),
                    ),
                  TextField(
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
                  if (_isUploading)
                    const Padding(
                      padding: EdgeInsets.only(top: 8),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF00A884)),
                          ),
                          SizedBox(width: 8),
                          Text(
                            'Uploading…',
                            style: TextStyle(color: Color(0xFF8696A0), fontSize: 12),
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 16),
            FilledButton(
              onPressed: isBusy
                  ? null
                  : () async {
                      final text = widget.textController.text.trim();
                      if (text.isEmpty && _pendingAttachments.isEmpty) return;
                      widget.onSend();
                      final senderId = context.read<UserController>().currentUser?.id;
                      await widget.controller.sendMessage(
                        text,
                        senderId: senderId,
                        attachments: _attachmentPayload,
                      );
                      if (mounted) {
                        widget.textController.clear();
                        setState(() {
                          _pendingAttachments.clear();
                        });
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

class _PendingAttachment {
  _PendingAttachment({
    required this.id,
    required this.filename,
    required this.mimeType,
    required this.url,
    required this.bytes,
  });

  final String id;
  final String filename;
  final String mimeType;
  final String url;
  final Uint8List bytes;

  Map<String, dynamic> toJson() => {
        'url': url,
        'filename': filename,
        'contentType': mimeType,
      };
}

class _AttachmentPreviewList extends StatelessWidget {
  const _AttachmentPreviewList({
    required this.attachments,
    required this.onRemove,
  });

  final List<_PendingAttachment> attachments;
  final ValueChanged<String> onRemove;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      children: attachments
          .map(
            (attachment) => Stack(
              clipBehavior: Clip.none,
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: Image.memory(
                    attachment.bytes,
                    width: 96,
                    height: 96,
                    fit: BoxFit.cover,
                  ),
                ),
                Positioned(
                  top: -8,
                  right: -8,
                  child: Material(
                    color: const Color(0xFF111B21),
                    shape: const CircleBorder(),
                    child: IconButton(
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                      iconSize: 18,
                      onPressed: () => onRemove(attachment.id),
                      icon: const Icon(Icons.close, color: Colors.white),
                      tooltip: 'Remove photo',
                    ),
                  ),
                ),
              ],
            ),
          )
          .toList(),
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

class _PendingAiActionRow extends StatelessWidget {
  const _PendingAiActionRow({required this.controller, required this.onRecovered});

  final ConversationController controller;
  final ValueChanged<String> onRecovered;

  @override
  Widget build(BuildContext context) {
    final isSending = controller.isSendingPendingAi;
    final isCancelling = controller.isCancellingPendingAi;
    final isDisabled = isSending || isCancelling;
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        FilledButton.icon(
          onPressed: isDisabled
              ? null
              : () async {
                  await controller.sendPendingAiNow();
                },
          icon: isSending
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Icon(Icons.send_rounded),
          label: Text(isSending ? 'Sending…' : 'Send now'),
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF00A884),
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          ),
        ),
        _EditScheduledButton(
          controller: controller,
          onRecovered: onRecovered,
        ),
      ],
    );
  }
}

class _EditScheduledButton extends StatelessWidget {
  const _EditScheduledButton({required this.controller, required this.onRecovered});

  final ConversationController controller;
  final ValueChanged<String> onRecovered;

  @override
  Widget build(BuildContext context) {
    final isBusy = controller.isCancellingPendingAi || controller.isSendingPendingAi;

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
