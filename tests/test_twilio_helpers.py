import types
import sys
from pathlib import Path

import pytest
from twilio.base.exceptions import TwilioRestException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from twilio_helpers import TwilioConfig, TwilioMessenger


class _FakeMessages:
    def __init__(self, responses):
        self._responses = responses
        self.calls = []
        self._index = 0

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses[self._index]
        self._index += 1
        if isinstance(response, Exception):
            raise response
        return response


def _make_messenger(*, messaging_service_sid="MG123", whatsapp_from="whatsapp:+15551234567"):
    config = TwilioConfig(
        account_sid="AC123",
        auth_token="token",
        whatsapp_from=whatsapp_from,
        messaging_service_sid=messaging_service_sid,
    )
    messenger = TwilioMessenger(config)
    return messenger


def test_send_whatsapp_message_falls_back_when_messaging_service_missing_channel(monkeypatch):
    messenger = _make_messenger()

    fake_messages = _FakeMessages(
        [
            TwilioRestException(400, "uri", msg="Twilio could not find a Channel with the specified From address", code=63007),
            types.SimpleNamespace(sid="SM123"),
        ]
    )
    messenger._client = types.SimpleNamespace(messages=fake_messages)

    sid = messenger.send_whatsapp_message(to="whatsapp:+447700900123", body="Hello!")

    assert sid == "SM123"
    assert fake_messages.calls == [
        {
            "to": "whatsapp:+447700900123",
            "body": "Hello!",
            "messaging_service_sid": "MG123",
        },
        {
            "to": "whatsapp:+447700900123",
            "body": "Hello!",
            "from_": "whatsapp:+15551234567",
        },
    ]


def test_send_whatsapp_message_raises_when_fallback_not_available(monkeypatch):
    messenger = _make_messenger(whatsapp_from=None)

    fake_messages = _FakeMessages(
        [
            TwilioRestException(400, "uri", msg="Twilio could not find a Channel with the specified From address", code=63007),
        ]
    )
    messenger._client = types.SimpleNamespace(messages=fake_messages)

    with pytest.raises(RuntimeError) as excinfo:
        messenger.send_whatsapp_message(to="whatsapp:+447700900123", body="Hello!")

    assert "Twilio could not find a Channel" in str(excinfo.value)
