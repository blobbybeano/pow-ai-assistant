import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/conversation.dart';

/// Default backend URL for local development.
/// Replace with your ngrok tunnel when testing on mobile.
const _defaultBaseUrl = 'http://127.0.0.1:5002';

class ChatApiClient {
  ChatApiClient({required this.baseUrl, http.Client? httpClient})
      : _client = httpClient ?? http.Client(),
        _baseUri = Uri.parse(baseUrl);

  factory ChatApiClient.fromEnvironment() {
    const baseUrl = String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: _defaultBaseUrl,
    );
    return ChatApiClient(baseUrl: baseUrl);
  }

  final String baseUrl;
  final http.Client _client;
  final Uri _baseUri;

  /// Releases any resources held by the underlying HTTP client.
  void close() {
    _client.close();
  }

  // --------------------------------------------------------------------------
  // Utility methods
  // --------------------------------------------------------------------------

  Map<String, dynamic> _decodeJsonMapResponse(
    http.Response response, {
    required String endpointDescription,
  }) {
    final rawBody = response.body;
    final body = rawBody.trim();
    if (body.isEmpty) {
      throw Exception(
        'Empty response from server when requesting $endpointDescription at $baseUrl. '
        'Confirm that API_BASE_URL points to the running backend.',
      );
    }

    try {
      final decoded = json.decode(body);
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return Map<String, dynamic>.from(decoded as Map);
      throw Exception(
        'Unexpected JSON structure when requesting $endpointDescription at $baseUrl. '
        'Expected an object but received ${decoded.runtimeType}.',
      );
    } on FormatException catch (error) {
      final normalisedSnippet = body
          .replaceAll(RegExp(r'\s+'), ' ')
          .replaceAll(RegExp(r'[\r\n]+'), ' ');
      final preview = normalisedSnippet.length > 160
          ? '${normalisedSnippet.substring(0, 160)}…'
          : normalisedSnippet;
      throw Exception(
        'Unexpected response format when requesting $endpointDescription at $baseUrl: '
        '${error.message}. Received "$preview".',
      );
    }
  }

  Iterable<String> _basePathSegments() {
    return _baseUri.pathSegments.where((segment) => segment.isNotEmpty);
  }

  Uri _uriFromSegments(
    Iterable<String> segments, {
    Map<String, String>? queryParameters,
  }) {
    final baseSegments = _basePathSegments().toList();
    final additionalSegments = segments
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();

    // Handle overlap between base and additional segments
    var overlap = 0;
    final maxOverlap =
        baseSegments.length < additionalSegments.length ? baseSegments.length : additionalSegments.length;

    for (var size = maxOverlap; size > 0; size--) {
      final baseTail = baseSegments.sublist(baseSegments.length - size);
      final segmentHead = additionalSegments.sublist(0, size);
      var matches = true;
      for (var i = 0; i < size; i++) {
        if (baseTail[i].toLowerCase() != segmentHead[i].toLowerCase()) {
          matches = false;
          break;
        }
      }
      if (matches) {
        overlap = size;
        break;
      }
    }

    final allSegments = [...baseSegments, ...additionalSegments.skip(overlap)];
    return Uri(
      scheme: _baseUri.scheme,
      host: _baseUri.host,
      port: _baseUri.port,
      pathSegments: allSegments,
      queryParameters: queryParameters,
    );
  }

  void _normaliseConversationPayload(Map<String, dynamic> payload,
      {String? conversationId}) {
    // Placeholder for your custom normalisation logic
  }

  void _normaliseMessagePayload(Map<String, dynamic> payload,
      {String? conversationId}) {
    // Placeholder for your custom normalisation logic
  }

  // --------------------------------------------------------------------------
  // API methods
  // --------------------------------------------------------------------------

  Future<List<ConversationSummary>> fetchConversations() async {
    try {
      final response =
          await _client.get(_uriFromSegments(const ['api', 'conversations']));
      if (response.statusCode != 200) {
        throw Exception('Failed to load conversations (${response.statusCode})');
      }

      final payload = _decodeJsonMapResponse(
        response,
        endpointDescription: 'fetchConversations',
      );

      final conversations = payload['conversations'] as List<dynamic>? ?? [];
      return conversations.map((json) {
        final map = Map<String, dynamic>.from(json as Map<String, dynamic>);
        final convoId = map['id'];
        _normaliseConversationPayload(
          map,
          conversationId: convoId is String ? convoId : null,
        );
        return ConversationSummary.fromJson(map);
      }).toList();
    } on SocketException {
      throw Exception('Network error: unable to reach $baseUrl');
    }
  }

  Future<ConversationDetail> fetchConversation(String conversationId) async {
    final response = await _client.get(
      _uriFromSegments(['api', 'conversations', conversationId]),
    );
    if (response.statusCode != 200) {
      throw Exception('Conversation request failed (${response.statusCode})');
    }

    final payload = _decodeJsonMapResponse(
      response,
      endpointDescription: 'conversation $conversationId',
    );

    _normaliseConversationPayload(payload, conversationId: conversationId);
    return ConversationDetail.fromJson(payload);
  }

  Future<bool> setAiEnabled(
    String conversationId,
    bool enabled, {
    String? responderId,
  }) async {
    final response = await _client.post(
      _uriFromSegments(['api', 'conversations', conversationId, 'toggle-ai']),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({
        'enabled': enabled,
        if (responderId != null) 'responderId': responderId,
      }),
    );
    if (response.statusCode != 200) {
      throw Exception('Unable to toggle AI (${response.statusCode})');
    }
    final payload = _decodeJsonMapResponse(
      response,
      endpointDescription: 'AI toggle for $conversationId',
    );
    return payload['enabled'] as bool? ?? enabled;
  }

  Future<String> sendManualMessage({
    required String conversationId,
    required String text,
    String? senderId,
  }) async {
    final response = await _client.post(
      _uriFromSegments(['api', 'conversations', conversationId, 'messages']),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({
        'text': text,
        if (senderId != null) 'senderId': senderId,
      }),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to send message (${response.statusCode})');
    }
    final payload = _decodeJsonMapResponse(
      response,
      endpointDescription: 'manual message send for $conversationId',
    );
    return payload['sid'] as String? ?? '';
  }

  Future<void> cancelScheduledMessage({
    required String conversationId,
    required String messageId,
  }) async {
    final response = await _client.post(
      _uriFromSegments([
        'api',
        'conversations',
        conversationId,
        'messages',
        messageId,
        'cancel',
      ]),
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
      _uriFromSegments([
        'api',
        'conversations',
        conversationId,
        'messages',
        messageId,
        'send-now',
      ]),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to send AI message now (${response.statusCode})');
    }
  }

  Future<String> fetchAiDraft(String conversationId, {String? responderId}) async {
    final body = responderId != null ? json.encode({'responderId': responderId}) : null;
    final headers = body != null ? {'Content-Type': 'application/json'} : null;
    final response = await _client.post(
      _uriFromSegments(['api', 'conversations', conversationId, 'ai-draft']),
      headers: headers,
      body: body,
    );
    if (response.statusCode != 200) {
      throw Exception('AI draft failed (${response.statusCode})');
    }
    final payload = _decodeJsonMapResponse(
      response,
      endpointDescription: 'AI draft for $conversationId',
    );
    return payload['draft'] as String;
  }

  Future<String?> fetchDefaultResponderId() async {
    final response = await _client.get(
      _uriFromSegments(const ['api', 'settings', 'responder']),
    );
    if (response.statusCode != 200 && response.statusCode != 404) {
      throw Exception('Failed to load responder preference (${response.statusCode})');
    }
    if (response.statusCode == 404 || response.body.isEmpty) return null;

    final contentType = response.headers['content-type']?.toLowerCase();
    final body = response.body.trim();
    final isLikelyJson =
        (contentType != null && contentType.contains('application/json')) ||
            body.startsWith('{') ||
            body.startsWith('[');
    if (!isLikelyJson) return null;

    try {
      final payload = json.decode(body) as Map<String, dynamic>;
      final value = payload['defaultResponderId'];
      return value is String && value.isNotEmpty ? value : null;
    } catch (_) {
      return null;
    }
  }

  Future<void> updateDefaultResponderId(String responderId) async {
    final response = await _client.post(
      _uriFromSegments(const ['api', 'settings', 'responder']),
      headers: const {'Content-Type': 'application/json'},
      body: json.encode({'responderId': responderId}),
    );

    if (response.statusCode != 200) {
      throw Exception(
        'Failed to persist responder preference (${response.statusCode})',
      );
    }
  }
}
