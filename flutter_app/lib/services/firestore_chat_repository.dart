import 'package:async/async.dart';
import 'package:cloud_firestore/cloud_firestore.dart';

import '../models/conversation.dart';
import '../models/message.dart';

class FirestoreChatRepository {
  FirestoreChatRepository({FirebaseFirestore? firestore})
      : _firestore = firestore ?? FirebaseFirestore.instance;

  final FirebaseFirestore _firestore;

  CollectionReference<Map<String, dynamic>> _conversationCollection(String accountId) {
    return _firestore.collection('accounts').doc(accountId).collection('conversations');
  }

  Stream<List<ConversationSummary>> watchConversations(String accountId) {
    final query = _conversationCollection(accountId)
        .orderBy('lastMessageAt', descending: true)
        .snapshots();
    return query.map(
      (snapshot) => snapshot.docs
          .map((doc) => ConversationSummary.fromFirestore(doc))
          .toList(),
    );
  }

  Stream<ConversationDetail> watchConversation(String accountId, String conversationId) {
    final conversationRef = _conversationCollection(accountId).doc(conversationId);
    final conversationStream = conversationRef.snapshots();
    final messagesStream = conversationRef
        .collection('messages')
        .orderBy('timestamp')
        .snapshots();

    return StreamZip([
      conversationStream,
      messagesStream,
    ]).map((events) {
      final convoSnapshot = events[0] as DocumentSnapshot<Map<String, dynamic>>;
      final messagesSnapshot = events[1] as QuerySnapshot<Map<String, dynamic>>;
      final messages = messagesSnapshot.docs
          .map((doc) => ChatMessage.fromMap({...doc.data(), 'id': doc.id}))
          .toList();
      return ConversationDetail.fromFirestore(convoSnapshot, messages: messages);
    });
  }

  Future<void> markConversationRead(String accountId, String conversationId) {
    return _conversationCollection(accountId).doc(conversationId).update({'unreadCount': 0});
  }
}
