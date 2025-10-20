import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/conversation.dart';
import '../models/message.dart';
import '../services/chat_api_client.dart';

class ConversationController extends ChangeNotifier {
  ConversationController({
    required this.apiClient,
    required this.conversationId,
    required this.initialDisplayName,
    String? initialResponderId,
  }) : _responderId = initialResponderId {
    _loadConversation();
    _pollingTimer = Timer.periodic(const Duration(seconds: 6), (_) => _loadConversation());
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (pendingAiMessage != null) {
        notifyListeners();
      }
    });
  }

  final ChatApiClient apiClient;
  final String conversationId;
  final String initialDisplayName;

  Timer? _pollingTimer;
  Timer? _countdownTimer;
  ConversationDetail? _detail;
  bool _loading = false;
  bool _sending = false;
  bool _drafting = false;
  bool _cancellingPendingAi = false;
  Object? _error;
  String? _aiDraft;
  String? _responderId;

  ConversationDetail? get detail => _detail;
  bool get isLoading => _loading;
  bool get isSending => _sending;
  bool get isDrafting => _drafting;
  bool get isCancellingPendingAi => _cancellingPendingAi;
  Object? get error => _error;
  bool get aiEnabled => _detail?.aiEnabled ?? true;
  String get displayName => _detail?.displayName ?? initialDisplayName;
  String? get aiDraft => _aiDraft;
  String? get responderId => _responderId;

  List<ChatMessage> get messages => _detail?.messages ?? [];

  ChatMessage? get pendingAiMessage {
    for (final message in messages.reversed) {
      if (message.author == 'ai' && (message.isScheduled || message.isDrafting)) {
        return message;
      }
    }
    return null;
  }

  Future<void> refresh() => _loadConversation(force: true);

  Future<String?> cancelPendingAiMessage() async {
    final pending = pendingAiMessage;
    if (pending == null) return null;
    final draftText = pending.text;
    _cancellingPendingAi = true;
    notifyListeners();
    try {
      await apiClient.cancelScheduledMessage(
        conversationId: conversationId,
        messageId: pending.id,
      );
      await _loadConversation(force: true);
      return draftText;
    } catch (error) {
      _error = error;
      notifyListeners();
      return null;
    } finally {
      _cancellingPendingAi = false;
      notifyListeners();
    }
  }

  Future<void> toggleAi(bool value) async {
    final previous = aiEnabled;
    try {
      final result = await apiClient.setAiEnabled(
        conversationId,
        value,
        responderId: _responderId,
      );
      _detail = _detail?.copyWith(aiEnabled: result);
      if (result) {
        _aiDraft = null;
      }
      notifyListeners();
      await _loadConversation(force: true);
    } catch (error) {
      _error = error;
      if (_detail != null) {
        _detail = _detail!.copyWith(aiEnabled: previous);
      }
      notifyListeners();
    }
  }

  Future<void> sendMessage(String text, {String? senderId}) async {
    if (text.trim().isEmpty) return;
    _sending = true;
    notifyListeners();

    try {
      await apiClient.sendManualMessage(
        conversationId: conversationId,
        text: text,
        senderId: senderId,
      );
      _aiDraft = null;
      await _loadConversation(force: true);
    } catch (error) {
      _error = error;
    } finally {
      _sending = false;
      notifyListeners();
    }
  }

  Future<void> fetchDraft() async {
    _drafting = true;
    notifyListeners();
    try {
      final draft = await apiClient.fetchAiDraft(
        conversationId,
        responderId: _responderId,
      );
      _aiDraft = draft;
    } catch (error) {
      _error = error;
    } finally {
      _drafting = false;
      notifyListeners();
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  void updateResponder(String? userId) {
    if (_responderId == userId) {
      return;
    }
    _responderId = userId;
    if (_aiDraft != null) {
      _aiDraft = null;
      notifyListeners();
    }
  }

  Future<void> _loadConversation({bool force = false}) async {
    if (_loading && !force) return;
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      final detail = await apiClient.fetchConversation(conversationId);
      _detail = detail;
    } catch (error) {
      _error = error;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _pollingTimer?.cancel();
    _countdownTimer?.cancel();
    super.dispose();
  }
}

extension on ConversationDetail {
  ConversationDetail copyWith({bool? aiEnabled, String? profilePhotoUrl}) {
    return ConversationDetail(
      id: id,
      phoneNumber: phoneNumber,
      displayName: displayName,
      aiEnabled: aiEnabled ?? this.aiEnabled,
      unreadCount: unreadCount,
      messages: List<ChatMessage>.from(messages),
      profilePhotoUrl: profilePhotoUrl ?? this.profilePhotoUrl,
    );
  }
}
