from flask import Flask, request
from twilio.rest import Client
import threading
import os

# Twilio credentials must be supplied through the environment.
ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_SMS_NUMBER = os.environ["TWILIO_SMS_NUMBER"]
TWILIO_WHATSAPP_NUMBER = os.environ["TWILIO_WHATSAPP_NUMBER"]

client = Client(ACCOUNT_SID, AUTH_TOKEN)
app = Flask(__name__)

# Store last incoming sender
last_sender = None


@app.route("/message", methods=["POST"])
@app.route("/twilio/whatsapp", methods=["POST"])  # Handles both webhook paths
def message():
    """Receive and print incoming messages from Twilio (SMS or WhatsApp)."""
    global last_sender
    sender = request.form.get("From")
    body = request.form.get("Body")

    print("\n📩 New message received!")
    print(f"From: {sender}")
    print(f"Body: {body}")

    last_sender = sender  # Save for quick replies
    return "Message received", 200


def normalize_number(to, msg_type):
    """
    Ensure number format matches the selected channel.
    - For WhatsApp: always 'whatsapp:+44...'
    - For SMS: plain '+44...'
    """
    to = to.strip()

    # Fix if user forgets to include country code (optional)
    if to.startswith("0"):
        to = "+44" + to[1:]

    if msg_type == "w":
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"
    else:
        # Remove accidental whatsapp: prefix for SMS
        to = to.replace("whatsapp:", "")

    return to


def send_message():
    """Allows manual sending of SMS or WhatsApp messages from the terminal."""
    global last_sender
    while True:
        print("\nOptions:")
        print("1. Reply to last sender")
        print("2. Send new message")
        choice = input("Select option (1 or 2): ").strip()

        if choice == "1" and last_sender:
            to = last_sender
            print(f"Replying to {to}")
            # Detect if last_sender is WhatsApp or SMS
            msg_type = "w" if "whatsapp:" in to else "s"
        elif choice == "2":
            msg_type = input("Send via [w]hatsapp or [s]ms? ").strip().lower()
            to = input("Enter recipient number (with country code or 0): ").strip()
            to = normalize_number(to, msg_type)
        else:
            print("⚠️ No recent sender to reply to.")
            continue

        body = input("Enter your message: ").strip()

        # Pick correct Twilio sender
        from_ = TWILIO_WHATSAPP_NUMBER if msg_type == "w" else TWILIO_SMS_NUMBER

        try:
            message = client.messages.create(from_=from_, to=to, body=body)
            print(f"✅ Sent message via {'WhatsApp' if msg_type == 'w' else 'SMS'} (SID: {message.sid})")
        except Exception as e:
            print(f"❌ Failed to send message: {e}")


def main():
    # Run Flask server in background
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=5002, debug=False, use_reloader=False)
    ).start()

    print("🚀 Listening for incoming messages on http://127.0.0.1:5002/message or /twilio/whatsapp")
    print("💬 You can reply or send new messages from this terminal.")
    send_message()


if __name__ == "__main__":
    main()
