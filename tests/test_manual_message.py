"""Tests for manual message sending behaviour in the Twilio Flask app."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import twilio_app
from conversation_store import ConversationStore


class ManualMessageTests(unittest.TestCase):
    """Exercise manual agent messages without relying on Twilio delivery."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        state_path = Path(self._tmp.name) / "state.json"
        self.store = ConversationStore(state_path, seed_demo=False)

        self.original_store = twilio_app.conversation_store
        self.original_messenger = twilio_app.twilio_messenger
        self.original_scheduled_ids = twilio_app._scheduled_message_ids.copy()

        twilio_app.conversation_store = self.store
        twilio_app.twilio_messenger = None
        twilio_app._scheduled_message_ids.clear()

        self.client = twilio_app.app.test_client()
        self.conversation_id = "+447700900123"

        # Seed a customer message so the conversation exists.
        self.store.record_message(
            self.conversation_id,
            text="Hello from a customer",
            author="customer",
            direction="inbound",
        )

    def tearDown(self) -> None:
        twilio_app.conversation_store = self.original_store
        twilio_app.twilio_messenger = self.original_messenger
        twilio_app._scheduled_message_ids.clear()
        twilio_app._scheduled_message_ids.update(self.original_scheduled_ids)
        self._tmp.cleanup()

    def test_manual_message_without_twilio_records_workspace_delivery(self) -> None:
        response = self.client.post(
            f"/api/conversations/{self.conversation_id}/messages",
            data=json.dumps({"text": "Hello!"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNotNone(payload)
        assert payload is not None  # for type checkers
        self.assertEqual(payload["status"], "sent")
        self.assertTrue(payload["sid"].startswith("local-"))
        self.assertEqual(payload["delivery"], "workspace")

        conversation = self.store.get_conversation(self.conversation_id)
        assert conversation is not None
        last_message = conversation["messages"][-1]
        self.assertEqual(last_message["author"], "agent")
        self.assertEqual(last_message["status"], "sent")
        self.assertEqual(last_message["via"], "workspace")

    def test_manual_message_cancels_pending_ai_and_assigns_responder(self) -> None:
        scheduled = self.store.record_message(
            self.conversation_id,
            text="Draft AI reply",
            author="ai",
            direction="outbound",
            status="scheduled",
            scheduled_send_at="2025-01-01T00:00:00+00:00",
        )
        twilio_app._scheduled_message_ids.add(scheduled.id)

        response = self.client.post(
            f"/api/conversations/{self.conversation_id}/messages",
            data=json.dumps({"text": "I'll take this", "senderId": "user-99"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        conversation = self.store.get_conversation(self.conversation_id)
        assert conversation is not None

        # Scheduled AI message is cancelled with a helpful reason.
        for message in conversation["messages"]:
            if message["id"] == scheduled.id:
                self.assertEqual(message["status"], "cancelled")
                self.assertEqual(
                    message["error"],
                    "Cancelled because an agent replied manually",
                )
                break
        else:  # pragma: no cover - guard against missing scheduled message
            self.fail("scheduled AI message was not found in conversation")

        self.assertNotIn(scheduled.id, twilio_app._scheduled_message_ids)
        self.assertEqual(conversation["assignedResponderId"], "user-99")


if __name__ == "__main__":  # pragma: no cover - manual execution guard
    unittest.main()
