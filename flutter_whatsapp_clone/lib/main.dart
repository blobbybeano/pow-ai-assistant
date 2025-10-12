import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';

void main() {
  runApp(const WhatsAppCloneApp());
}

class WhatsAppCloneApp extends StatelessWidget {
  const WhatsAppCloneApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'POW Chat',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF128C7E),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      home: const ChatHomePage(),
    );
  }
}

class UserProfile {
  const UserProfile({
    required this.id,
    required this.displayName,
    required this.bubbleDecoration,
    required this.avatarColor,
  });

  final String id;
  final String displayName;
  final BoxDecoration bubbleDecoration;
  final Color avatarColor;
}

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.authorId,
    required this.text,
    required this.timestamp,
    required this.isAI,
  });

  final String id;
  final String authorId;
  final String text;
  final DateTime timestamp;
  final bool isAI;
}

class ChatHomePage extends StatefulWidget {
  const ChatHomePage({super.key});

  @override
  State<ChatHomePage> createState() => _ChatHomePageState();
}

class _ChatHomePageState extends State<ChatHomePage> {
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final List<ChatMessage> _messages = <ChatMessage>[];
  late final Map<String, UserProfile> _profiles;

  String _activeUserId = 'u1';
  bool _aiEnabled = true;
  bool _aiIsTyping = false;
  ChatMessage? _previewMessage;
  Timer? _aiTimer;

  @override
  void initState() {
    super.initState();
    _profiles = _buildProfiles();
  }

  @override
  void dispose() {
    _messageController.dispose();
    _scrollController.dispose();
    _aiTimer?.cancel();
    super.dispose();
  }

  Map<String, UserProfile> _buildProfiles() {
    return <String, UserProfile>{
      'u1': UserProfile(
        id: 'u1',
        displayName: 'Alex',
        avatarColor: const Color(0xFF075E54),
        bubbleDecoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: <Color>[Color(0xFFDCF8C6), Color(0xFFCFFFD8)],
          ),
          borderRadius: BorderRadius.circular(16),
        ),
      ),
      'u2': UserProfile(
        id: 'u2',
        displayName: 'Jordan',
        avatarColor: const Color(0xFF25D366),
        bubbleDecoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: <Color>[Color(0xFFECE5DD), Color(0xFFDAD0C2)],
          ),
          borderRadius: BorderRadius.circular(16),
        ),
      ),
      'ai': UserProfile(
        id: 'ai',
        displayName: 'AI Assistant',
        avatarColor: const Color(0xFF34B7F1),
        bubbleDecoration: BoxDecoration(
          color: const Color(0xFFE0F7FA),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFF81D4FA)),
        ),
      ),
    };
  }

  void _sendMessage({required String text, required String senderId, bool isAI = false}) {
    if (text.trim().isEmpty) {
      return;
    }

    final ChatMessage message = ChatMessage(
      id: UniqueKey().toString(),
      authorId: senderId,
      text: text.trim(),
      timestamp: DateTime.now(),
      isAI: isAI,
    );

    setState(() {
      _messages.add(message);
    });

    _scrollToBottom();
  }

  void _onSubmitMessage() {
    final String rawText = _messageController.text;
    if (rawText.trim().isEmpty) {
      return;
    }

    _messageController.clear();
    _cancelPendingAI();
    _sendMessage(text: rawText, senderId: _activeUserId);

    if (_aiEnabled) {
      _scheduleAIResponse();
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) {
        return;
      }
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent + 80,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    });
  }

  void _scheduleAIResponse() {
    final ChatMessage? lastHumanMessage = _messages.lastWhere(
      (ChatMessage message) => message.authorId != 'ai',
      orElse: () => ChatMessage(
        id: 'placeholder',
        authorId: _activeUserId,
        text: '',
        timestamp: DateTime.now(),
        isAI: false,
      ),
    );

    final String previewText = _generateAIResponse(lastHumanMessage.text);
    _previewMessage = ChatMessage(
      id: 'preview',
      authorId: 'ai',
      text: previewText,
      timestamp: DateTime.now(),
      isAI: true,
    );

    setState(() {
      _aiIsTyping = true;
    });

    _aiTimer = Timer(const Duration(seconds: 3), () {
      if (!_aiIsTyping || _previewMessage == null) {
        return;
      }
      _finalizeAIResponse();
    });
  }

  void _finalizeAIResponse() {
    final ChatMessage? preview = _previewMessage;
    if (preview == null) {
      return;
    }

    _sendMessage(text: preview.text, senderId: preview.authorId, isAI: true);
    setState(() {
      _previewMessage = null;
      _aiIsTyping = false;
    });
  }

  void _cancelPendingAI() {
    _aiTimer?.cancel();
    setState(() {
      _aiIsTyping = false;
      _previewMessage = null;
    });
  }

  String _generateAIResponse(String prompt) {
    final String cleanedPrompt = prompt.trim();
    if (cleanedPrompt.isEmpty) {
      return 'Sure thing! How can I assist everyone in this chat?';
    }

    final List<String> templates = <String>[
      'I noticed "$cleanedPrompt". Here\'s what I can add…',
      'Building on "$cleanedPrompt", here\'s my suggestion.',
      'Great point about "$cleanedPrompt". I recommend the following.',
      'To respond to "$cleanedPrompt", we could try this approach.',
      'Let me think aloud: "$cleanedPrompt". My answer would be…',
    ];

    final Random random = Random();
    return templates[random.nextInt(templates.length)];
  }

  @override
  Widget build(BuildContext context) {
    final Iterable<UserProfile> participants = _profiles.values.where(
      (UserProfile profile) => profile.id != 'ai',
    );

    return Scaffold(
      appBar: AppBar(
        title: const Text('POW WhatsApp Prototype'),
        actions: <Widget>[
          Tooltip(
            message: _aiEnabled
                ? 'AI auto replies are enabled'
                : 'AI auto replies are paused',
            child: Row(
              children: <Widget>[
                const Text('AI'),
                Switch(
                  value: _aiEnabled,
                  onChanged: (bool value) {
                    setState(() {
                      _aiEnabled = value;
                    });
                    if (!value) {
                      _cancelPendingAI();
                    }
                  },
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Send previewed AI response now',
            onPressed: _aiIsTyping ? _finalizeAIResponse : null,
            icon: const Icon(Icons.send_and_archive),
          ),
          IconButton(
            tooltip: 'Cancel pending AI response',
            onPressed: _aiIsTyping ? _cancelPendingAI : null,
            icon: const Icon(Icons.cancel_schedule_send),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            _buildParticipantsHeader(participants),
            const Divider(height: 1),
            Expanded(child: _buildMessageList()),
            if (_aiIsTyping && _previewMessage != null)
              _buildAiPreviewCard(_previewMessage!),
            _buildComposer(),
          ],
        ),
      ),
    );
  }

  Widget _buildParticipantsHeader(Iterable<UserProfile> participants) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: participants
                  .map(
                    (UserProfile profile) => Chip(
                      avatar: CircleAvatar(
                        backgroundColor: profile.avatarColor,
                        child: Text(profile.displayName.characters.first),
                      ),
                      label: Text(profile.displayName),
                    ),
                  )
                  .toList(),
            ),
          ),
          const SizedBox(width: 12),
          DropdownButton<String>(
            value: _activeUserId,
            underline: const SizedBox.shrink(),
            onChanged: (String? value) {
              if (value == null) {
                return;
              }
              setState(() {
                _activeUserId = value;
              });
            },
            items: participants
                .map(
                  (UserProfile profile) => DropdownMenuItem<String>(
                    value: profile.id,
                    child: Text('Send as ${profile.displayName}'),
                  ),
                )
                .toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildMessageList() {
    if (_messages.isEmpty) {
      return const Center(
        child: Text(
          'Start the conversation! The AI assistant can join when enabled.',
          textAlign: TextAlign.center,
        ),
      );
    }

    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
      itemCount: _messages.length,
      itemBuilder: (BuildContext context, int index) {
        final ChatMessage message = _messages[index];
        final UserProfile profile = _profiles[message.authorId]!;
        final Alignment alignment =
            message.authorId == 'ai' ? Alignment.center : Alignment.centerLeft;
        final CrossAxisAlignment columnAlignment =
            message.authorId == 'ai' ? CrossAxisAlignment.center : CrossAxisAlignment.start;

        return Align(
          alignment: alignment,
          child: Container(
            margin: const EdgeInsets.symmetric(vertical: 4),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: profile.bubbleDecoration,
            constraints: const BoxConstraints(maxWidth: 420),
            child: Column(
              crossAxisAlignment: columnAlignment,
              children: <Widget>[
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    CircleAvatar(
                      radius: 10,
                      backgroundColor: profile.avatarColor,
                      child: Text(
                        profile.displayName.characters.first,
                        style: const TextStyle(fontSize: 12, color: Colors.white),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      profile.displayName + (message.isAI ? ' (AI)' : ''),
                      style: TextStyle(
                        fontWeight:
                            message.authorId == _activeUserId && !message.isAI
                                ? FontWeight.bold
                                : FontWeight.w600,
                        color: Colors.black87,
                      ),
                    ),
                    if (message.authorId == _activeUserId && !message.isAI)
                      const Padding(
                        padding: EdgeInsets.only(left: 4),
                        child: Icon(Icons.edit, size: 14, color: Colors.black54),
                      ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  message.text,
                  style: const TextStyle(fontSize: 15, height: 1.3),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: Text(
                    _formatTimestamp(message.timestamp),
                    style: const TextStyle(fontSize: 11, color: Colors.black54),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildAiPreviewCard(ChatMessage preview) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFEDF8FF),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF34B7F1)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const SizedBox(
            width: 32,
            height: 32,
            child: CircularProgressIndicator(strokeWidth: 3),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  'AI drafting…',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 4),
                Text(
                  preview.text,
                  style: const TextStyle(fontStyle: FontStyle.italic),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  children: <Widget>[
                    ElevatedButton.icon(
                      onPressed: _finalizeAIResponse,
                      icon: const Icon(Icons.send),
                      label: const Text('Send as shown'),
                    ),
                    OutlinedButton.icon(
                      onPressed: _cancelPendingAI,
                      icon: const Icon(Icons.cancel),
                      label: const Text('Cancel'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildComposer() {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        boxShadow: const <BoxShadow>[
          BoxShadow(blurRadius: 6, color: Colors.black12),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: <Widget>[
            Expanded(
              child: TextField(
                controller: _messageController,
                minLines: 1,
                maxLines: 4,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(
                  hintText: 'Message',
                  border: OutlineInputBorder(),
                ),
                onSubmitted: (_) => _onSubmitMessage(),
              ),
            ),
            const SizedBox(width: 12),
            IconButton(
              icon: const Icon(Icons.send),
              color: Theme.of(context).colorScheme.primary,
              onPressed: _onSubmitMessage,
            ),
          ],
        ),
      ),
    );
  }

  String _formatTimestamp(DateTime timestamp) {
    final TimeOfDay timeOfDay = TimeOfDay.fromDateTime(timestamp);
    final String hour = timeOfDay.hourOfPeriod.toString().padLeft(2, '0');
    final String minute = timeOfDay.minute.toString().padLeft(2, '0');
    final String period = timeOfDay.period == DayPeriod.am ? 'AM' : 'PM';
    return '$hour:$minute $period';
  }
}
