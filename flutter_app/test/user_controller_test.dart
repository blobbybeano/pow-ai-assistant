import 'package:flutter_test/flutter_test.dart';

import 'package:powwash_workspace/controllers/user_controller.dart';
import 'package:powwash_workspace/models/conversation.dart';

void main() {
  group('UserController', () {
    test('includes unassigned conversations for the active user', () {
      final controller = UserController();
      controller.signIn('user-1');

      final conversations = [
        ConversationSummary(
          id: '+15551230001',
          phoneNumber: '+15551230001',
          displayName: 'Alex Martinez',
          aiEnabled: true,
          unreadCount: 0,
        ),
        ConversationSummary(
          id: '+447366320940',
          phoneNumber: '+447366320940',
          displayName: 'Ben',
          aiEnabled: true,
          unreadCount: 2,
        ),
        ConversationSummary(
          id: '+14085550100',
          phoneNumber: '+14085550100',
          displayName: 'Jordan Lee',
          aiEnabled: true,
          unreadCount: 0,
        ),
      ];

      final visible = controller.assignedConversations(conversations);

      expect(visible.map((c) => c.id), contains('+15551230001'));
      expect(visible.map((c) => c.id), contains('+447366320940'));
      expect(visible.map((c) => c.id), isNot(contains('+14085550100')));
    });

    test('keeps responding user selection after signing out', () {
      final controller = UserController();
      controller.signIn('user-1');
      controller.switchRespondingUser('user-2');

      controller.signOut();

      expect(controller.respondingUser?.id, 'user-2');

      controller.signIn('user-1');
      expect(controller.respondingUser?.id, 'user-2');
    });
  });
}
