import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/conversation.dart';
import '../services/chat_api_client.dart';

class InboxController extends ChangeNotifier {
  InboxController({required this.apiClient}) {
    _refreshInbox();
    _pollingTimer = Timer.periodic(const Duration(seconds: 8), (_) => _refreshInbox());
  }

  final ChatApiClient apiClient;
  Timer? _pollingTimer;
  List<ConversationSummary> _conversations = [];
  bool _loading = false;
  Object? _error;

  List<ConversationSummary> get conversations => _conversations;
  bool get isLoading => _loading;
  Object? get error => _error;
  List<ConversationSummary> get pendingAiConversations => _conversations
      .where(
        (conversation) =>
            conversation.lastMessage != null &&
            conversation.lastMessage!.author == 'ai' &&
            conversation.lastMessage!.isPending,
      )
      .toList();

  Future<void> refresh() => _refreshInbox(force: true);

  Future<void> _refreshInbox({bool force = false}) async {
    if (_loading && !force) return;
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final items = await apiClient.fetchConversations();
      _conversations = items;
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
