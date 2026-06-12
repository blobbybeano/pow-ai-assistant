import 'package:flutter/foundation.dart';

class ProfileController extends ChangeNotifier {
  final Map<String, String> _photosByConversation = {};

  String? photoFor(String conversationId) => _photosByConversation[conversationId];

  void setPhoto(String conversationId, String? url) {
    final trimmed = url?.trim();
    if (trimmed == null || trimmed.isEmpty) {
      if (_photosByConversation.remove(conversationId) != null) {
        notifyListeners();
      }
      return;
    }

    if (_photosByConversation[conversationId] == trimmed) {
      return;
    }

    _photosByConversation[conversationId] = trimmed;
    notifyListeners();
  }

  Map<String, String> get allPhotos => Map.unmodifiable(_photosByConversation);
}
