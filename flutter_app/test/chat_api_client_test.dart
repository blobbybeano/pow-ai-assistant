import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:powwash_workspace/services/chat_api_client.dart';

void main() {
  test('fetchConversations uses baseUrl without duplicating path segments', () async {
    late Uri requested;
    final client = MockClient((request) async {
      requested = request.url;
      return http.Response(json.encode({'conversations': []}), 200);
    });

    final api = ChatApiClient(baseUrl: 'https://example.com/api', httpClient: client);
    await api.fetchConversations();

    expect(requested.toString(), 'https://example.com/api/conversations');
    api.close();
  });

  test('fetchConversation respects nested base paths', () async {
    late Uri requested;
    final client = MockClient((request) async {
      requested = request.url;
      final payload = {
        'id': '+123',
        'phoneNumber': '+123',
        'displayName': '+123',
        'aiEnabled': true,
        'unreadCount': 0,
        'messages': [],
      };
      return http.Response(json.encode(payload), 200);
    });

    final api = ChatApiClient(
      baseUrl: 'https://example.com/workspace/api',
      httpClient: client,
    );

    await api.fetchConversation('+123');

    expect(
      requested.toString(),
      'https://example.com/workspace/api/conversations/%2B123',
    );
    api.close();
  });
}
