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

  Future<bool> setAiEnabled(
    String conversationId,
    bool enabled, {
    String? responderId,
  }) async {
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/toggle-ai'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({
        'enabled': enabled,
        if (responderId != null) 'responderId': responderId,
      }),
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
    String? senderId,
  }) async {
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/messages'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({
        'text': text,
        if (senderId != null) 'senderId': senderId,
      }),
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

  Future<void> sendScheduledMessageNow({
    required String conversationId,
    required String messageId,
  }) async {
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/messages/$messageId/send-now'),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to send AI message now (${response.statusCode})');
    }
  }

  Future<String> fetchAiDraft(String conversationId, {String? responderId}) async {
    final body = responderId != null ? json.encode({'responderId': responderId}) : null;
    final headers = body != null ? {'Content-Type': 'application/json'} : null;
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/ai-draft'),
      headers: headers,
      body: body,
    );
    if (response.statusCode != 200) {
      throw Exception('AI draft failed (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    return payload['draft'] as String;
  }

  Future<String?> fetchDefaultResponderId() async {
    final response = await _client.get(_uri('/api/settings/responder'));
    if (response.statusCode != 200 && response.statusCode != 404) {
      throw Exception('Failed to load responder preference (${response.statusCode})');
    }
    if (response.statusCode == 404 || response.body.isEmpty) {
      return null;
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    final value = payload['defaultResponderId'];
    return value is String && value.isNotEmpty ? value : null;
  }

  Future<void> updateDefaultResponderId(String responderId) async {
    final response = await _client.post(
      _uri('/api/settings/responder'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'responderId': responderId}),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to persist responder preference (${response.statusCode})');
    }
  }

  void close() {
    _client.close();
  }
}
