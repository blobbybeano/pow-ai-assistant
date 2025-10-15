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
  }) {
    _loadConversation();
    _pollingTimer = Timer.periodic(const Duration(seconds: 6), (_) => _loadConversation());
  }

  final ChatApiClient apiClient;
  final String conversationId;
  final String initialDisplayName;

  Timer? _pollingTimer;
  ConversationDetail? _detail;
  bool _loading = false;
  bool _sending = false;
  bool _drafting = false;
  Object? _error;
  String? _aiDraft;

  ConversationDetail? get detail => _detail;
  bool get isLoading => _loading;
  bool get isSending => _sending;
  bool get isDrafting => _drafting;
  Object? get error => _error;
  bool get aiEnabled => _detail?.aiEnabled ?? true;
  String get displayName => _detail?.displayName ?? initialDisplayName;
  String? get aiDraft => _aiDraft;

  List<ChatMessage> get messages => _detail?.messages ?? [];

  Future<void> toggleAi(bool value) async {
    try {
      final result = await apiClient.setAiEnabled(conversationId, value);
      _detail = _detail?.copyWith(aiEnabled: result);
      if (result) {
        _aiDraft = null;
      }
    } catch (error) {
      _error = error;
    }
    notifyListeners();
  }

  Future<void> sendMessage(String text) async {
    if (text.trim().isEmpty) return;
    _sending = true;
    notifyListeners();

    try {
      await apiClient.sendManualMessage(conversationId: conversationId, text: text);
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
      final draft = await apiClient.fetchAiDraft(conversationId);
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
    super.dispose();
  }
}

extension on ConversationDetail {
  ConversationDetail copyWith({bool? aiEnabled}) {
    return ConversationDetail(
      id: id,
      phoneNumber: phoneNumber,
      displayName: displayName,
      aiEnabled: aiEnabled ?? this.aiEnabled,
      unreadCount: unreadCount,
      messages: List<ChatMessage>.from(messages),
    );
  }
}
