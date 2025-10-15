"""Twilio webhook that drafts PowWash replies with the OpenAI auto responder."""
from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, request
from twilio.twiml.messaging_response import MessagingResponse

from auto_responder import generate_reply
import os
print("✅ Flask sees OPENAI_API_KEY:", bool(os.getenv("OPENAI_API_KEY")))



app = Flask(__name__)

PRICE_LIST_PATH = Path("price_list.json")
TONE_PROFILE_PATH = Path("tone_profile.md")


def _build_reply(inbound_text: str) -> str:
    """Generate a PowWash response for the inbound WhatsApp message."""
    if not inbound_text:
        return (
            "Hi there! This is PowWash. I didn't catch your message—"
            "could you please resend it so we can prepare your quote?"
        )

    return generate_reply(
        message=inbound_text,
        price_list_path=PRICE_LIST_PATH,
        tone_profile_path=TONE_PROFILE_PATH,
        model="gpt-4o-mini",
        temperature=0.5,
    )


@app.post("/twilio/whatsapp")
def whatsapp_webhook() -> Response:
    """Return a TwiML response with the drafted PowWash reply."""
    inbound_text = request.form.get("Body", "").strip()

    reply_text = _build_reply(inbound_text)

    response = MessagingResponse()
    response.message(reply_text)

    return Response(str(response), mimetype="application/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
