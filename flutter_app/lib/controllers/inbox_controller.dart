import 'dart:async';

import 'package:flutter/foundation.dart';

import '../models/conversation.dart';
import '../services/firestore_chat_repository.dart';

class InboxController extends ChangeNotifier {
  InboxController({required this.chatRepository});

  final FirestoreChatRepository chatRepository;
  StreamSubscription<List<ConversationSummary>>? _subscription;
  String? _accountId;
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

  void updateAccount(String? accountId) {
    if (_accountId == accountId) return;
    _subscription?.cancel();
    _accountId = accountId;
    _conversations = [];
    _loading = accountId != null;
    _error = null;
    notifyListeners();

    if (accountId == null) return;

    _subscription = chatRepository.watchConversations(accountId).listen(
      (items) {
        _conversations = items;
        _loading = false;
        _error = null;
        notifyListeners();
      },
      onError: (err) {
        _error = err;
        _loading = false;
        notifyListeners();
      },
    );
  }

  Future<void> refresh() async {
    if (_accountId == null) return;
    updateAccount(_accountId);
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }
}
