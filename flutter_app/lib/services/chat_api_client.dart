import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/conversation.dart';
import '../models/integration_settings.dart';
import '../models/quote_request.dart';

typedef TokenProvider = Future<String?> Function();

class ChatApiClient {
  ChatApiClient({
    required this.baseUrl,
    http.Client? httpClient,
    this.tokenProvider,
  }) : _client = httpClient ?? http.Client();

  factory ChatApiClient.fromEnvironment({TokenProvider? tokenProvider}) {
    const defaultUrl = String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: 'http://127.0.0.1:5002',
    );
    return ChatApiClient(baseUrl: defaultUrl, tokenProvider: tokenProvider);
  }

  Future<IntegrationSettings> fetchIntegrationSettings() async {
    final response = await _client.get(
      _uri('/api/settings/integrations'),
      headers: await _withAuthHeaders(),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to load integration settings (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    return IntegrationSettings.fromJson(payload);
  }

  Future<IntegrationSettings> updateIntegrationSettings(
    IntegrationSettingsUpdate update,
  ) async {
    final response = await _client.post(
      _uri('/api/settings/integrations'),
      headers: await _withAuthHeaders({'Content-Type': 'application/json'}),
      body: json.encode(update.toJson()),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to save integration settings (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    return IntegrationSettings.fromJson(payload);
  }

  final String baseUrl;
  final http.Client _client;
  final TokenProvider? tokenProvider;

  Uri _uri(String path) {
    final base = Uri.parse(baseUrl);
    return base.resolve(path);
  }

  Future<Map<String, String>> _withAuthHeaders([
    Map<String, String>? additional,
  ]) async {
    final headers = <String, String>{...?additional};
    if (tokenProvider != null) {
      final token = await tokenProvider!.call();
      if (token != null && token.isNotEmpty) {
        headers['Authorization'] = 'Bearer $token';
      }
    }
    return headers;
  }

  Future<List<ConversationSummary>> fetchConversations() async {
    final response = await _client.get(
      _uri('/api/conversations'),
      headers: await _withAuthHeaders(),
    );
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
    final response = await _client.get(
      _uri('/api/conversations/$conversationId'),
      headers: await _withAuthHeaders(),
    );
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
      headers: await _withAuthHeaders({'Content-Type': 'application/json'}),
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
      headers: await _withAuthHeaders({'Content-Type': 'application/json'}),
      body: json.encode({
        'text': text,
        if (senderId != null) 'senderId': senderId,
      }),
    );
    if (response.statusCode != 200 && response.statusCode != 202) {
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
      headers: await _withAuthHeaders(),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to cancel AI message (${response.statusCode})');
    }
  }

  Future<String> fetchAiDraft(String conversationId, {String? responderId}) async {
    final body = responderId != null ? json.encode({'responderId': responderId}) : null;
    final headers = body != null ? {'Content-Type': 'application/json'} : null;
    final response = await _client.post(
      _uri('/api/conversations/$conversationId/ai-draft'),
      headers: await _withAuthHeaders(headers),
      body: body,
    );
    if (response.statusCode != 200) {
      throw Exception('AI draft failed (${response.statusCode})');
    }
    final payload = json.decode(response.body) as Map<String, dynamic>;
    return payload['draft'] as String;
  }

  Future<String?> fetchDefaultResponderId() async {
    final response = await _client.get(
      _uri('/api/settings/responder'),
      headers: await _withAuthHeaders(),
    );
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
      headers: await _withAuthHeaders({'Content-Type': 'application/json'}),
      body: json.encode({'responderId': responderId}),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to persist responder preference (${response.statusCode})');
    }
  }

  Future<ConnectionTestResult> testTwilioConnection() async {
    return _postConnectionTest('/api/settings/test-twilio');
  }

  Future<ConnectionTestResult> testOpenAiConnection() async {
    return _postConnectionTest('/api/settings/test-openai');
  }

  Future<ConnectionTestResult> _postConnectionTest(String path) async {
    final response = await _client.post(
      _uri(path),
      headers: await _withAuthHeaders(),
    );
    final payload = response.body.isNotEmpty
        ? json.decode(response.body) as Map<String, dynamic>
        : <String, dynamic>{};
    final ok = payload['ok'] == true;
    final message = payload['message'] as String? ??
        (ok ? 'Connection validated successfully.' : 'Connection test failed.');
    final identifier = (payload['serviceSid'] ?? payload['modelId'] ?? payload['id']) as String?;
    return ConnectionTestResult(ok: ok, message: message, identifier: identifier);
  }

  Future<List<QuoteRequest>> fetchQuoteRequests() async {
    final response = await _client.get(
      _uri('/api/quote-requests'),
      headers: await _withAuthHeaders(),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to load quote requests (${response.statusCode})');
    }
    final list = json.decode(response.body) as List<dynamic>;
    return list
        .map((e) => QuoteRequest.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> answerQuoteRequest(String id, String advice) async {
    final response = await _client.post(
      _uri('/api/quote-requests/${Uri.encodeComponent(id)}/answer'),
      headers: await _withAuthHeaders({'Content-Type': 'application/json'}),
      body: json.encode({'advice': advice}),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to answer quote request (${response.statusCode})');
    }
  }

  Future<void> dismissQuoteRequest(String id) async {
    final response = await _client.delete(
      _uri('/api/quote-requests/${Uri.encodeComponent(id)}'),
      headers: await _withAuthHeaders(),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to dismiss quote request (${response.statusCode})');
    }
  }

  void close() {
    _client.close();
  }
}

class ConnectionTestResult {
  const ConnectionTestResult({required this.ok, required this.message, this.identifier});

  final bool ok;
  final String message;
  final String? identifier;
}
