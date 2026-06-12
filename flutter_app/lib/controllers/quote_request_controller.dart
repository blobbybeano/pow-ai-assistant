import 'package:flutter/foundation.dart';

import '../models/quote_request.dart';
import '../services/chat_api_client.dart';

class QuoteRequestController extends ChangeNotifier {
  QuoteRequestController({required this.apiClient}) {
    refresh();
  }

  final ChatApiClient apiClient;

  List<QuoteRequest> _requests = [];
  bool _loading = false;
  Object? _error;

  List<QuoteRequest> get requests => _requests;
  bool get isLoading => _loading;
  Object? get error => _error;

  int get pendingCount =>
      _requests.where((r) => r.isPending).length;

  Future<void> refresh() async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      _requests = await apiClient.fetchQuoteRequests();
    } catch (e) {
      _error = e;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> answer(String id, String advice) async {
    try {
      await apiClient.answerQuoteRequest(id, advice);
      await refresh();
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> dismiss(String id) async {
    try {
      await apiClient.dismissQuoteRequest(id);
      await refresh();
      return true;
    } catch (_) {
      return false;
    }
  }
}
