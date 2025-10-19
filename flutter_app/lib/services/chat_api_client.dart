import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/conversation.dart';

class ChatApiClient {
  ChatApiClient({required this.baseUrl, http.Client? httpClient})
      : _client = httpClient ?? http.Client();

  factory ChatApiClient.fromEnvironment() {
    const defaultUrl = String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: 'http://127.0.0.1:5002',
    );
    return ChatApiClient(baseUrl: defaultUrl);
  }

  final String baseUrl;
  final http.Client _client;

  Uri _uri(String path) {
    final base = Uri.parse(baseUrl);
    return base.resolve(path);
  }

  Future<List<ConversationSummary>> fetchConversations() async {
    final response = await _client.get(_uri('/api/conversations'));
    if (response.statusCode != 200) {
      throw Exception('Failed to load conversations (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    final conversations = payload['conversations'] as List<dynamic>? ?? [];
    return conversations
        .map((json) => ConversationSummary.fromJson(json as Map<String, dynamic>))
        .toList();
  }

  Future<ConversationDetail> fetchConversation(String conversationId) async {
    final response = await _client.get(_uri('/api/conversations/$conversationId'));
    if (response.statusCode != 200) {
      throw Exception('Conversation request failed (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    return ConversationDetail.fromJson(payload);
  }

  Future<bool> setAiEnabled(String conversationId, bool enabled) async {
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/toggle-ai'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'enabled': enabled}),
    );
    if (response.statusCode != 200) {
      throw Exception('Unable to toggle AI (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    return payload['enabled'] as bool? ?? enabled;
  }

  Future<String> sendManualMessage({
    required String conversationId,
    required String text,
  }) async {
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/messages'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'text': text}),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to send message (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    return payload['sid'] as String? ?? '';
  }

  Future<void> cancelScheduledMessage({
    required String conversationId,
    required String messageId,
  }) async {
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/messages/$messageId/cancel'),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to cancel AI message (${response.statusCode})');
    }
  }

  Future<String> fetchAiDraft(String conversationId) async {
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/ai-draft'),
    );
    if (response.statusCode != 200) {
      throw Exception('AI draft failed (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    return payload['draft'] as String;
  }

  void close() {
    _client.close();
  }
}
